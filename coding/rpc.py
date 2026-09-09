"""JSON-lines RPC over stdin/stdout, so a non-Python frontend can drive the agent.

Same shape as tau's src/tau_coding/rpc.py: read one JSON object per line,
write one JSON object per line.

  in   {"type": "prompt", "text": "..."}   {"type": "cancel"}
       {"type": "new_session"}   {"type": "list_sessions"}
       {"type": "resume", "id": "<prefix>"}
  out  {"type": "TextDeltaEvent", "delta": "..."}  ...  {"type": "turn_end"}
       {"type": "session", "session_id": "...", "messages": [...]}
       {"type": "sessions", "rows": [{"id": ..., "updated_at": ...}]}
       {"type": "notice", "text": "..."}
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ai.openai import OpenAIProvider
from coding.chat_session_manager import ChatSessionManager
from coding.context import (
    discover_project_context,
    discover_skills,
    format_project_context,
    format_skills,
)
from coding.extensions.loader import load_extensions_from_dir
from coding.extensions.runtime import ExtensionRuntime
from coding.session import CodingSession, CodingSessionConfig
from coding.tools import (
    create_bash_tool,
    create_edit_tool,
    create_read_tool,
    create_write_tool,
)

system_prompt = """
You are helpful assistant. You have access to user filesystem.
"""

# CodingSession.prompt() prints to stdout (session.py:145, :155). That would
# corrupt the protocol, so the real stdout is claimed here and everything else
# is pushed to stderr.
_out = sys.stdout
sys.stdout = sys.stderr


def emit(obj: dict):
    _out.write(json.dumps(obj) + "\n")
    _out.flush()


async def build_config() -> CodingSessionConfig:
    cwd = Path.cwd()

    dynamic_system_prompt = (
        system_prompt.strip()
        + format_project_context(discover_project_context(cwd))
        + format_skills(discover_skills(cwd))
    )

    extension_runtime = ExtensionRuntime()
    extension_dir = cwd / ".mini-pi" / "extensions"
    extension_dir.mkdir(parents=True, exist_ok=True)
    await load_extensions_from_dir(extension_dir, extension_runtime)

    return CodingSessionConfig(
        provider=OpenAIProvider(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        ),
        model=os.getenv("MODEL"),
        system=dynamic_system_prompt,
        tools=[
            create_bash_tool(),
            create_read_tool(),
            create_write_tool(),
            create_edit_tool(),
        ],
        storage=None,  # set per session below
        auto_compact_threshold=50_000,
        extension_runtime=extension_runtime,
    )


async def run_turn(session: CodingSession, text: str):
    try:
        async for event in session.prompt(text):
            emit({"type": type(event).__name__, **event.model_dump(mode="json")})
    except Exception as exc:
        emit({"type": "AssistantErrorEvent", "error": str(exc)})
    finally:
        emit({"type": "turn_end"})


async def main():
    config = await build_config()
    manager = ChatSessionManager()

    async def switch(session_id: str, storage) -> CodingSession:
        config.storage = storage
        session = await CodingSession.load(config)
        emit(
            {
                "type": "session",
                "session_id": session_id,
                "messages": [
                    m.model_dump(mode="json") for m in session.harness.messages
                ],
            }
        )
        return session

    session_id, storage = manager.new_session_storage()
    session = await switch(session_id, storage)
    emit({"type": "ready", "session_id": session_id, "model": os.getenv("MODEL")})

    reader = asyncio.StreamReader()
    await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
    )

    turn: asyncio.Task | None = None
    running = lambda: turn is not None and not turn.done()

    while True:
        line = await reader.readline()
        if not line:
            break

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = msg.get("type")

        if kind == "prompt":
            if running():
                continue
            turn = asyncio.create_task(run_turn(session, msg.get("text", "")))

        elif kind == "cancel":
            session.cancel()

        elif kind == "list_sessions":
            emit(
                {
                    "type": "sessions",
                    "rows": [r.model_dump(mode="json") for r in manager.list_sessions()],
                }
            )

        elif kind in ("new_session", "resume"):
            if running():
                emit({"type": "notice", "text": "Busy — cancel the turn first."})
                continue

            if kind == "new_session":
                session_id, storage = manager.new_session_storage()
            else:
                matched = manager.get_session_storage(msg.get("id", ""))
                if matched is None:
                    emit({"type": "notice", "text": f"No session with '{msg.get('id')}'"})
                    continue
                session_id, storage = matched

            session = await switch(session_id, storage)

    if running():
        turn.cancel()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
