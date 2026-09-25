import asyncio
from collections.abc import Callable
import json
import sys
import uuid

from dotenv import load_dotenv

from ai.registry import get_api_key, get_model
from coding.auth import remove_api_key_from_auth, set_api_key_to_auth
from coding.events import SessionEvent
from coding.extensions.types import ExtensionUIContext
from coding.session_manager.manager import list_sessions
from coding.rpc_types import (
    CompactRequest,
    EmptySuccessResponse,
    ExtensionCommandInfo,
    ExtensionCommandsData,
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
from coding.session_runtime import CodingSessionRuntime
from coding.settings import set_default_model

_out = sys.stdout  # _out = fd_1
sys.stdout = sys.stderr  # sys.stdout --> fd_2
# Write to fd_1 i.e out_1 still goes to stdout
# normal print use sys.stdout so they go to fd_2


def emit(obj: dict):
    _out.write(json.dumps(obj) + "\n")
    _out.flush()


def write_event(event: SessionEvent) -> None:
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
    session_unsubscribe: Callable[[], None] | None = None

    def rebind_session(session: CodingSession) -> None:
        nonlocal session_unsubscribe

        if session_unsubscribe is not None:
            session_unsubscribe()

        session_unsubscribe = session.subscribe(write_event)

    config = await build_session_config()
    pending_ui_tasks: dict[str, asyncio.Future[ExtensionUIResponse]] = {}
    config.extension_runtime.context.ui = RpcExtensionUI(pending_ui_tasks)

    session_runtime = await CodingSessionRuntime.create(config)
    session_runtime.set_rebind_session(rebind_session)
    rebind_session(session_runtime.session)

    # empty Stream reader buffer in memory not pointed to any fd yet
    reader = asyncio.StreamReader()

    # Connect reader to fd
    await asyncio.get_event_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
    )

    loop_task: asyncio.Task | None = None

    is_running = lambda: loop_task is not None and not loop_task.done()

    async def handle_line(line: bytes):
        nonlocal loop_task

        try:
            rpc_client_msg = json.loads(line)
        except Exception as exc:
            send_response(
                RpcErrorResponse(
                    request_type="parse_error",
                    error=f"Invalid json: {exc}",
                )
            )
            return

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

            return

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
            return

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
                    return

                loop_task = asyncio.create_task(
                    session_runtime.session.prompt(
                        content=rpc_request.message,
                    )
                )
            elif rpc_request.type == RequestTypes.STEER:
                await session_runtime.session.steer(
                    rpc_request.message,
                )
            elif rpc_request.type == RequestTypes.FOLLOW_UP:
                await session_runtime.session.follow_up(
                    rpc_request.message,
                )
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
                return

            try:
                await session_runtime.session.compact(
                    custom_instructions=rpc_request.custom_instructions,
                    reason="manual",
                )

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
                return

            try:
                await session_runtime.switch_session(rpc_request.session_id)
            except ValueError as err:
                send_response(
                    RpcErrorResponse(
                        request_type=RequestTypes.RESUME,
                        id=rpc_request.id,
                        error=str(err),
                    )
                )
                return

            send_response(
                RpcPayloadResponse(
                    request_type=RequestTypes.RESUME,
                    id=rpc_request.id,
                    data=SessionData(
                        session_id=session_runtime.session.chat_session_manager.session_id,
                        messages=session_runtime.session.harness.messages,
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
                return

            entry_id = rpc_request.entry_id

            try:
                messages = await session_runtime.session.rewind_to(entry_id)
                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.REWIND,
                        id=rpc_request.id,
                        data=SessionData(
                            session_id=session_runtime.session.chat_session_manager.session_id,
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

                session_runtime.session.set_model(
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
                return

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
                        data=SessionState(
                            model=session_runtime.session.config.model.name
                        ),
                    )
                )
            elif rpc_request.type == RequestTypes.NEW_SESSION:
                await session_runtime.new_session()
                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.NEW_SESSION,
                        id=rpc_request.id,
                        data=SessionData(
                            session_id=session_runtime.session.chat_session_manager.session_id,
                            messages=[],
                        ),
                    )
                )
            elif rpc_request.type == RequestTypes.GET_REWIND_TARGETS:
                targets = await session_runtime.session.get_rewind_targets()
                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.GET_REWIND_TARGETS,
                        id=rpc_request.id,
                        data=RewindTargetsData(targets=targets),
                    )
                )
            elif rpc_request.type == RequestTypes.GET_EXTENSION_COMMANDS:
                extension_runtime = session_runtime.session.config.extension_runtime
                commands = (
                    extension_runtime.get_all_commands()
                    if extension_runtime is not None
                    else []
                )

                send_response(
                    RpcPayloadResponse(
                        request_type=RequestTypes.GET_EXTENSION_COMMANDS,
                        id=rpc_request.id,
                        data=ExtensionCommandsData(
                            commands=[
                                ExtensionCommandInfo(
                                    name=c.name, description=c.description
                                )
                                for c in commands
                            ]
                        ),
                    )
                )
            elif rpc_request.type == RequestTypes.ABORT:
                session_runtime.session.cancel()
                send_response(
                    EmptySuccessResponse(
                        request_type=RequestTypes.ABORT,
                        id=rpc_request.id,
                    )
                )

    line_tasks: set[asyncio.Task] = set()
    # asyncio.create_task mention to keep reference for the task ourself otherwise
    # running task can be garbage collected before it finishes

    while True:
        line = await reader.readline()

        if not line:
            break

        task = asyncio.create_task(handle_line(line))
        line_tasks.add(task)
        task.add_done_callback(line_tasks.discard)

    if is_running():
        session_runtime.session.cancel()


if __name__ == "__main__":
    load_dotenv()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodBye")
