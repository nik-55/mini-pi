import asyncio
import json
import sys
from typing import Any

from dotenv import load_dotenv

from coding.chat_session_manager import ChatSessionManager
from coding.rpc_types import (
    CompactRequest,
    GeneralRequest,
    MessageRequest,
    RequestTypes,
    ResumeRequest,
    RewindRequest,
    RpcResponse,
    RpcResponseRequestType,
    rpc_request_adapter,
)
from coding.session import CodingSession
from coding.session_factory import build_session_config

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


def send_response(
    request_type: RpcResponseRequestType,
    success: bool,
    id: str | None = None,
    data: Any = None,
    error: str | None = None,
):
    resp = RpcResponse(
        id=id,
        request_type=request_type,
        success=success,
        data=data,
        error=error,
    )

    emit(resp.model_dump(mode="json"))


async def main():
    session_manager = ChatSessionManager()
    session_id, storage = session_manager.new_session_storage()

    config = await build_session_config(storage=storage)

    coding_session = await CodingSession.load(config)

    # empty Stream reader buffer in memory not pointed to any fd yet
    reader = asyncio.StreamReader()

    # Connect reader to fd
    await asyncio.get_event_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
    )

    loop_task: asyncio.Task | None = None

    is_running = lambda: loop_task is not None and not loop_task.done()

    emit({"type": "ready", "model": config.model})

    # At server startup, create new session
    emit({"type": "session", "session_id": session_id, "messages": []})

    while True:
        line = await reader.readline()

        if not line:
            break

        try:
            rpc_client_msg = json.loads(line)
        except Exception as exc:
            send_response(
                request_type="parse_error",
                success=False,
                error=f"Invalid json: {exc}",
            )
            continue

        try:
            rpc_request = rpc_request_adapter.validate_python(rpc_client_msg)
        except Exception as exc:
            req_id: str | None = None

            if isinstance(rpc_client_msg, dict):
                req_id = rpc_client_msg.get("id")

            send_response(
                request_type="parse_error",
                id=req_id,
                success=False,
                error=f"Invalid request: {exc}",
            )
            continue

        if isinstance(rpc_request, MessageRequest):
            if rpc_request.type == RequestTypes.PROMPT:
                if is_running():
                    send_response(
                        request_type=rpc_request.type,
                        id=rpc_request.id,
                        success=False,
                        error="Agent is already running",
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
                request_type=rpc_request.type,
                id=rpc_request.id,
                success=True,
            )
        elif isinstance(rpc_request, CompactRequest):
            if is_running():
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=False,
                    error="Agent is already running",
                )
                continue

            try:
                compaction_resp = await coding_session.compact(
                    custom_instructions=rpc_request.custom_instructions,
                )
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=True,
                    data={"response": compaction_resp},
                )
            except Exception as exc:
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=False,
                    error=f"Compaction failed: {exc}",
                )

        elif isinstance(rpc_request, ResumeRequest):
            if is_running():
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=False,
                    error="Agent is already running",
                )
                continue

            matched = session_manager.get_session_storage(rpc_request.session_id)

            if matched is None:
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=False,
                    error=f"No session matching '{rpc_request.session_id}'",
                )
                continue

            session_id, storage = matched
            config.storage = storage
            coding_session = await CodingSession.load(config)

            send_response(
                request_type=rpc_request.type,
                id=rpc_request.id,
                success=True,
                data={
                    "session_id": session_id,
                    "messages": [
                        m.model_dump(mode="json")
                        for m in coding_session.harness.messages
                    ],
                },
            )
        elif isinstance(rpc_request, RewindRequest):
            if is_running():
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=False,
                    error="Agent is already running",
                )
                continue

            entry_id = rpc_request.entry_id

            try:
                messages = await coding_session.rewind_to(entry_id)
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=True,
                    data={
                        "session_id": session_id,
                        "messages": [m.model_dump(mode="json") for m in messages],
                    },
                )
            except Exception as exc:
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=False,
                    error=f"Rewind is failed: {exc}",
                )
        elif isinstance(rpc_request, GeneralRequest):
            if rpc_request.type == RequestTypes.LIST_SESSIONS:
                session_rows = [
                    r.model_dump(mode="json") for r in session_manager.list_sessions()
                ]
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=True,
                    data={"rows": session_rows},
                )
            elif rpc_request.type == RequestTypes.GET_STATE:
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=True,
                    data={
                        "model": config.model,
                    },
                )
            elif rpc_request.type == RequestTypes.NEW_SESSION:
                if is_running():
                    send_response(
                        request_type=rpc_request.type,
                        id=rpc_request.id,
                        success=False,
                        error="Agent is running",
                    )
                    continue

                session_id, storage = session_manager.new_session_storage()
                config.storage = storage
                coding_session = await CodingSession.load(config)
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=True,
                    data={"session_id": session_id, "messages": []},
                )
            elif rpc_request.type == RequestTypes.GET_REWIND_TARGETS:
                targets = await coding_session.get_rewind_targets()
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=True,
                    data={
                        "targets": [t.model_dump(mode="json") for t in targets],
                    },
                )
            elif rpc_request.type == RequestTypes.ABORT:
                coding_session.cancel()
                send_response(
                    request_type=rpc_request.type,
                    id=rpc_request.id,
                    success=True,
                )

    if is_running():
        coding_session.cancel()


if __name__ == "__main__":
    load_dotenv()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodBye")
