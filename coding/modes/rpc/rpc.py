import asyncio
from collections.abc import Callable
import json
import sys

from ai.registry import get_api_key, get_model
from coding.auth import remove_api_key_from_auth, set_api_key_to_auth
from coding.session_manager.manager import list_sessions
from coding.modes.rpc.extension_ui import RpcExtensionUI
from coding.modes.rpc.output import send_response, write_event
from coding.modes.rpc.types import (
    EmptySuccessResponse,
    ExtensionCommandInfo,
    ExtensionCommandsData,
    RequestTypes,
    RewindTargetsData,
    RpcErrorResponse,
    RpcPayloadResponse,
    RpcRequest,
    RpcResponse,
    SessionData,
    SessionListData,
    SessionState,
    rpc_request_adapter,
    ExtensionUIResponse,
)
from coding.session import CodingSession
from coding.session_runtime import CodingSessionRuntime
from coding.settings import set_default_model


async def handle_request(
    request: RpcRequest, session_runtime: CodingSessionRuntime
) -> RpcResponse | None:
    # Messages
    if request.type == RequestTypes.PROMPT:
        send_response(
            EmptySuccessResponse(
                request_type=RequestTypes.PROMPT,
                id=request.id,
            )
        )
        await session_runtime.session.prompt(
            content=request.message,
        )
        return

    if request.type == RequestTypes.STEER:
        await session_runtime.session.steer(
            request.message,
        )
        return EmptySuccessResponse(
            request_type=RequestTypes.STEER,
            id=request.id,
        )

    if request.type == RequestTypes.FOLLOW_UP:
        await session_runtime.session.follow_up(
            request.message,
        )

        return EmptySuccessResponse(
            request_type=RequestTypes.FOLLOW_UP,
            id=request.id,
        )

    # Compact
    if request.type == RequestTypes.COMPACT:
        await session_runtime.session.compact(
            custom_instructions=request.custom_instructions,
            reason="manual",
        )

        return EmptySuccessResponse(
            request_type=RequestTypes.COMPACT,
            id=request.id,
        )

    # Tree related
    if request.type == RequestTypes.REWIND:
        entry_id = request.entry_id

        messages = await session_runtime.session.rewind_to(entry_id)
        return RpcPayloadResponse(
            request_type=RequestTypes.REWIND,
            id=request.id,
            data=SessionData(
                session_id=session_runtime.session.chat_session_manager.session_id,
                messages=messages,
            ),
        )

    # Auth and settings
    if request.type == RequestTypes.LOGIN:
        set_api_key_to_auth(request.provider, request.key)

        return EmptySuccessResponse(
            request_type=RequestTypes.LOGIN,
            id=request.id,
        )

    if request.type == RequestTypes.LOGOUT:
        remove_api_key_from_auth(request.provider)

        return EmptySuccessResponse(
            request_type=RequestTypes.LOGOUT,
            id=request.id,
        )

    if request.type == RequestTypes.SET_DEFAULT_MODEL:
        ai_model = get_model(request.model_ref)
        api_key = get_api_key(ai_model.provider)

        if not api_key:
            raise ValueError(f"API key missing for provider: {ai_model.provider}")

        set_default_model(request.model_ref)

        session_runtime.session.set_model(
            ai_model,
        )

        return EmptySuccessResponse(
            request_type=RequestTypes.SET_DEFAULT_MODEL,
            id=request.id,
        )

    # Sessions
    if request.type == RequestTypes.LIST_SESSIONS:
        session_rows = list_sessions()
        return RpcPayloadResponse(
            request_type=RequestTypes.LIST_SESSIONS,
            id=request.id,
            data=SessionListData(rows=session_rows),
        )

    if request.type == RequestTypes.GET_STATE:
        return RpcPayloadResponse(
            request_type=RequestTypes.GET_STATE,
            id=request.id,
            data=SessionState(model=session_runtime.session.config.model.name),
        )

    if request.type == RequestTypes.NEW_SESSION:
        await session_runtime.new_session()
        return RpcPayloadResponse(
            request_type=RequestTypes.NEW_SESSION,
            id=request.id,
            data=SessionData(
                session_id=session_runtime.session.chat_session_manager.session_id,
                messages=[],
            ),
        )

    if request.type == RequestTypes.RESUME:
        await session_runtime.switch_session(request.session_id)

        return RpcPayloadResponse(
            request_type=RequestTypes.RESUME,
            id=request.id,
            data=SessionData(
                session_id=session_runtime.session.chat_session_manager.session_id,
                messages=session_runtime.session.harness.messages,
            ),
        )

    if request.type == RequestTypes.GET_REWIND_TARGETS:
        targets = await session_runtime.session.get_rewind_targets()
        return RpcPayloadResponse(
            request_type=RequestTypes.GET_REWIND_TARGETS,
            id=request.id,
            data=RewindTargetsData(targets=targets),
        )

    # Commands
    if request.type == RequestTypes.GET_EXTENSION_COMMANDS:
        extension_runtime = session_runtime.session.config.extension_runtime
        commands = (
            extension_runtime.get_all_commands()
            if extension_runtime is not None
            else []
        )

        return RpcPayloadResponse(
            request_type=RequestTypes.GET_EXTENSION_COMMANDS,
            id=request.id,
            data=ExtensionCommandsData(
                commands=[
                    ExtensionCommandInfo(name=c.name, description=c.description)
                    for c in commands
                ]
            ),
        )

    # Abort
    if request.type == RequestTypes.ABORT:
        session_runtime.session.cancel()
        return EmptySuccessResponse(
            request_type=RequestTypes.ABORT,
            id=request.id,
        )


async def run_rpc_mode(session_runtime: CodingSessionRuntime) -> None:
    session_unsubscribe: Callable[[], None] | None = None
    pending_ui_tasks: dict[str, asyncio.Future[ExtensionUIResponse]] = {}

    def rebind_session(new_session: CodingSession) -> None:
        nonlocal session_unsubscribe

        if session_unsubscribe is not None:
            session_unsubscribe()

        if new_session.config.extension_runtime is not None:
            new_session.config.extension_runtime.context.ui = RpcExtensionUI(
                pending_ui_tasks
            )

        session_unsubscribe = new_session.subscribe(write_event)

    session_runtime.set_rebind_session(rebind_session)
    rebind_session(session_runtime.session)

    # empty Stream reader buffer in memory not pointed to any fd yet
    reader = asyncio.StreamReader()

    # Connect reader to fd
    await asyncio.get_event_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
    )

    async def handle_line(line: bytes):
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

        try:
            response = await handle_request(
                request=rpc_request, session_runtime=session_runtime
            )

            if response is not None:
                send_response(response)

        except Exception as exc:
            send_response(
                RpcErrorResponse(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    error=str(exc),
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

    for task in line_tasks:
        task.cancel()

    if line_tasks:
        # wait for task to cancel. If task hang (i.e it dont respect cancel) so here
        # we will also hang which is expected behavioor
        await asyncio.gather(*line_tasks, return_exceptions=True)
