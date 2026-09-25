import asyncio
import json
import sys
import uuid

from dotenv import load_dotenv

from ai.registry import get_api_key, get_model
from coding.auth import remove_api_key_from_auth, set_api_key_to_auth
from coding.extensions.types import ExtensionUIContext
from coding.session_manager.manager import ChatSessionManager, list_sessions
from coding.rpc_types import (
    CompactRequest,
    EmptySuccessResponse,
    GeneralRequest,
    LoginRequest,
    LogoutRequest,
    MessageRequest,
    RequestTypes,
    ResumeRequest,
    RewindRequest,
    RewindTargetsData,
    RpcErrorResponse,
    RpcPayloadResponse,
    RpcResponse,
    SessionData,
    SessionListData,
    SessionState,
    SetDefaultModelRequest,
    rpc_request_adapter,
    ExtensionUIRequest,
    ExtensionUIResponse,
    NotifyUIRequestPayload,
    SelectUIRequestPayload,
)
from coding.session import CodingSession
from coding.session_factory import build_session_config
from coding.settings import set_default_model

_out = sys.stdout  # _out = fd_1
sys.stdout = sys.stderr  # sys.stdout --> fd_2
# Write to fd_1 i.e out_1 still goes to stdout
# normal print use sys.stdout so they go to fd_2


def emit(obj: dict):
    _out.write(json.dumps(obj) + "\n")
    _out.flush()


async def run_loop(coding_session: CodingSession, text: str):
    async for event in coding_session.prompt(text):
        emit(event.model_dump(mode="json"))


def send_response(resp: RpcResponse):
    emit(resp.model_dump(mode="json"))


class RpcExtensionUI(ExtensionUIContext):
    def __init__(
        self,
        pending_ui_tasks: dict[str, asyncio.Future[ExtensionUIResponse]],
    ):
        self.pending_ui_tasks = pending_ui_tasks

    async def select(self, title: str, options: list[str]) -> str | None:
        req = ExtensionUIRequest(
            id=uuid.uuid4().hex[:6],
            payload=SelectUIRequestPayload(title=title, options=options),
        )

        future: asyncio.Future[ExtensionUIResponse] = (
            asyncio.get_event_loop().create_future()
        )

        self.pending_ui_tasks[req.id] = future

        emit(req.model_dump(mode="json"))

        try:
            resp = await future
        finally:
            self.pending_ui_tasks.pop(req.id, None)

        if resp.cancelled:
            return

        return resp.value

    def notify(self, message: str, level: str = "info") -> None:
        req = ExtensionUIRequest(
            id=uuid.uuid4().hex[:6],
            payload=NotifyUIRequestPayload(message=message, notify_type=level),
        )

        emit(req.model_dump(mode="json"))


async def main():
    config = await build_session_config(
        chat_session_manager=ChatSessionManager.new_session()
    )
    pending_ui_tasks: dict[str, asyncio.Future[ExtensionUIResponse]] = {}
    config.extension_runtime.context.ui = RpcExtensionUI(pending_ui_tasks)

    coding_session = await CodingSession.load(config)

    # empty Stream reader buffer in memory not pointed to any fd yet
    reader = asyncio.StreamReader()

    # Connect reader to fd
    await asyncio.get_event_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
    )

    loop_task: asyncio.Task | None = None

    is_running = lambda: loop_task is not None and not loop_task.done()

    while True:
        line = await reader.readline()

        if not line:
            break

        try:
            rpc_client_msg = json.loads(line)
        except Exception as exc:
            send_response(
                RpcErrorResponse(
                    request_type="parse_error",
                    error=f"Invalid json: {exc}",
                )
            )
            continue

        # Check if it is extension UI response
        if (
            isinstance(rpc_client_msg, dict)
            and rpc_client_msg.get("type") == "extension_ui_response"
        ):
            try:
                extension_ui_res = ExtensionUIResponse.model_validate(rpc_client_msg)

                pending_future = pending_ui_tasks.get(extension_ui_res.id)

                if pending_future is not None and not pending_future.done():
                    pending_future.set_result(extension_ui_res)
            except Exception as exc:
                pass

            continue

        try:
            rpc_request = rpc_request_adapter.validate_python(rpc_client_msg)
        except Exception as exc:
            req_id: str | None = None

            if isinstance(rpc_client_msg, dict):
                req_id = rpc_client_msg.get("id")

            send_response(
                RpcErrorResponse(
                    request_type="parse_error",
                    id=req_id,
                    error=f"Invalid request: {exc}",
                )
            )
            continue

        if isinstance(rpc_request, MessageRequest):
            if rpc_request.type == RequestTypes.PROMPT:
                if is_running():
                    send_response(
                        RpcErrorResponse(
                            request_type=rpc_request.type,
                            id=rpc_request.id,
                            error="Agent is already running",
                        )
                    )
                    continue

                loop_task = asyncio.create_task(
                    run_loop(
                        coding_session,
                        text=rpc_request.message,
                    )
                )
            elif rpc_request.type == RequestTypes.STEER:
                async for _ in coding_session.prompt(
                    rpc_request.message,
                    streaming_behaviour="steer",
                ):
                    pass
            elif rpc_request.type == RequestTypes.FOLLOW_UP:
                async for _ in coding_session.prompt(
                    rpc_request.message,
                    streaming_behaviour="follow_up",
                ):
                    pass

            send_response(
                EmptySuccessResponse(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                ),
            )
        elif isinstance(rpc_request, CompactRequest):
            if is_running():
                send_response(
                    RpcErrorResponse(
                        request_type=rpc_request.type,
                        id=rpc_request.id,
                        error="Agent is already running",
                    )
                )
                continue

            try:
                async for event in coding_session.compact(
                    custom_instructions=rpc_request.custom_instructions,
                    reason="manual",
                ):
                    emit(event.model_dump(mode="json"))

                send_response(
                    EmptySuccessResponse(
                        request_type=RequestTypes.COMPACT,
                        id=rpc_request.id,
                    )
                )
            except Exception as exc:
                send_response(
                    RpcErrorResponse(
                        request_type=RequestTypes.COMPACT,
                        id=rpc_request.id,
                        error=f"Compaction failed: {exc}",
                    )
                )

        elif isinstance(rpc_request, ResumeRequest):
            if is_running():
                send_response(
                    RpcErrorResponse(
                        request_type=RequestTypes.RESUME,
                        id=rpc_request.id,
                        error="Agent is already running",
                    )
                )
                continue

            new_chat_session_manager = ChatSessionManager.search_session(
                rpc_request.session_id,
                cwd=config.chat_session_manager.cwd,
            )

            if new_chat_session_manager is None:
                send_response(
                    RpcErrorResponse(
                        request_type=RequestTypes.RESUME,
                        id=rpc_request.id,
                        error=f"No session matching '{rpc_request.session_id}'",
                    )
                )
                continue

            config.chat_session_manager = new_chat_session_manager
            coding_session = await CodingSession.load(config)

            send_response(
                RpcPayloadResponse(
                    request_type=RequestTypes.RESUME,
                    id=rpc_request.id,
                    data=SessionData(
                        session_id=new_chat_session_manager.session_id,
                        messages=coding_session.harness.messages,
                    ),
                )
            )
        elif isinstance(rpc_request, RewindRequest):
            if is_running():
                send_response(
                    RpcErrorResponse(
                        request_type=rpc_request.type,
                        id=rpc_request.id,
                        error="Agent is already running",
                    )
                )
                continue

            entry_id = rpc_request.entry_id

            try:
                messages = await coding_session.rewind_to(entry_id)
                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.REWIND,
                        id=rpc_request.id,
                        data=SessionData(
                            session_id=config.chat_session_manager.session_id,
                            messages=messages,
                        ),
                    ),
                )
            except Exception as exc:
                send_response(
                    RpcErrorResponse(
                        request_type=RequestTypes.REWIND,
                        id=rpc_request.id,
                        error=f"Rewind is failed: {exc}",
                    )
                )
        elif isinstance(rpc_request, LoginRequest):
            set_api_key_to_auth(rpc_request.provider, rpc_request.key)

            send_response(
                EmptySuccessResponse(
                    request_type=RequestTypes.LOGIN,
                    id=rpc_request.id,
                )
            )
        elif isinstance(rpc_request, LogoutRequest):
            remove_api_key_from_auth(rpc_request.provider)

            send_response(
                EmptySuccessResponse(
                    request_type=RequestTypes.LOGOUT,
                    id=rpc_request.id,
                )
            )
        elif isinstance(rpc_request, SetDefaultModelRequest):
            try:
                ai_model = get_model(rpc_request.model_ref)
                api_key = get_api_key(ai_model.provider)

                if not api_key:
                    raise ValueError(
                        f"API key missing for provider: {ai_model.provider}"
                    )

                set_default_model(rpc_request.model_ref)

                coding_session.set_model(
                    ai_model,
                )

                send_response(
                    EmptySuccessResponse(
                        request_type=RequestTypes.SET_DEFAULT_MODEL,
                        id=rpc_request.id,
                    )
                )
            except Exception as err:
                send_response(
                    RpcErrorResponse(
                        request_type=RequestTypes.SET_DEFAULT_MODEL,
                        id=rpc_request.id,
                        error=str(err),
                    )
                )

        elif isinstance(rpc_request, GeneralRequest):
            if is_running() and rpc_request.type != RequestTypes.ABORT:
                send_response(
                    RpcErrorResponse(
                        request_type=rpc_request.type,
                        id=rpc_request.id,
                        error="Agent is running",
                    )
                )
                continue

            if rpc_request.type == RequestTypes.LIST_SESSIONS:
                session_rows = list_sessions()
                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.LIST_SESSIONS,
                        id=rpc_request.id,
                        data=SessionListData(rows=session_rows),
                    )
                )
            elif rpc_request.type == RequestTypes.GET_STATE:
                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.GET_STATE,
                        id=rpc_request.id,
                        data=SessionState(model=config.model.name),
                    )
                )
            elif rpc_request.type == RequestTypes.NEW_SESSION:
                new_chat_session_manager = ChatSessionManager.new_session(
                    cwd=config.chat_session_manager.cwd
                )
                config.chat_session_manager = new_chat_session_manager
                coding_session = await CodingSession.load(config)
                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.NEW_SESSION,
                        id=rpc_request.id,
                        data=SessionData(
                            session_id=new_chat_session_manager.session_id, messages=[]
                        ),
                    )
                )
            elif rpc_request.type == RequestTypes.GET_REWIND_TARGETS:
                targets = await coding_session.get_rewind_targets()
                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.GET_REWIND_TARGETS,
                        id=rpc_request.id,
                        data=RewindTargetsData(targets=targets),
                    )
                )
            elif rpc_request.type == RequestTypes.ABORT:
                coding_session.cancel()
                send_response(
                    EmptySuccessResponse(
                        request_type=RequestTypes.ABORT,
                        id=rpc_request.id,
                    )
                )

    if is_running():
        coding_session.cancel()


if __name__ == "__main__":
    load_dotenv()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodBye")
