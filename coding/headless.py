import asyncio
import json
import sys

from dotenv import load_dotenv

from coding.chat_session_manager import ChatSessionManager
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
    try:
        async for event in coding_session.prompt(text):
            emit({"type": type(event).__name__, **event.model_dump(mode="json")})
    except Exception as exc:
        emit({"type": "AssistantErrorEvent", "error": str(exc)})
    finally:
        emit({"type": "loop_end"})


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
            continue

        kind = rpc_client_msg.get("type", None)

        if kind == "prompt":
            if is_running():
                emit(
                    {
                        "type": "notice",
                        "text": "Unsupported while agent is already running",
                    }
                )
                continue

            loop_task = asyncio.create_task(
                run_loop(coding_session, rpc_client_msg.get("text", ""))
            )
        elif kind == "cancel":
            coding_session.cancel()
        elif kind == "list_sessions":
            session_rows = [
                r.model_dump(mode="json") for r in session_manager.list_sessions()
            ]
            emit({"type": "sessions", "rows": session_rows})
        elif kind == "new_session":
            if is_running():
                emit({"type": "notice", "text": "Cancel the loop first"})
                continue

            session_id, storage = session_manager.new_session_storage()
            config.storage = storage
            coding_session = await CodingSession.load(config)

            emit({"type": "session", "session_id": session_id, "messages": []})
        elif kind == "resume":
            if is_running():
                emit({"type": "notice", "text": "Cancel the loop first"})
                continue

            target_id = rpc_client_msg.get("id", "")
            matched = session_manager.get_session_storage(target_id)

            if matched is None:
                emit({"type": "notice", "text": f"No session matching '{target_id}'"})
                continue

            session_id, storage = matched
            config.storage = storage
            coding_session = await CodingSession.load(config)

            emit(
                {
                    "type": "session",
                    "session_id": session_id,
                    "messages": [
                        m.model_dump(mode="json")
                        for m in coding_session.harness.messages
                    ],
                }
            )

    if is_running():
        coding_session.cancel()


if __name__ == "__main__":
    load_dotenv()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodBye")
