import asyncio
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from agent.events import (
    AssistantErrorEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from agent.messages import (
    AgentMessage,
    AssistantMessage,
    ToolResultMessage,
    UserMessage,
)
from ai.openai import OpenAIProvider
from coding.context import (
    discover_project_context,
    discover_skills,
    format_project_context,
    format_skills,
)
from coding.extensions.loader import load_extensions_from_dir
from coding.tools import (
    create_edit_tool,
    create_read_tool,
    create_bash_tool,
    create_write_tool,
)
from coding.session import CodingSessionConfig, CodingSession
from coding.chat_session_manager import ChatSessionManager
from coding.extensions.runtime import ExtensionRuntime

system_prompt = """
You are helpful assistant. You have access to user filesystem.
"""


def clear_screen():
    sys.stdout.write("\033[2J\033[3J\033[H")
    sys.stdout.flush()


def print_session_history(messages: list[AgentMessage]):
    for msg in messages:
        if isinstance(msg, UserMessage):
            print(f"user> {msg.content}\n")
        elif isinstance(msg, AssistantMessage):
            print(f"assistant> ", end="", flush=True)
            if msg.thinking:
                print(f"|start_thinking|\n\033[90m{msg.thinking}\033[0m\n")
            if msg.content:
                print(f"{msg.content}\n", flush=True)

            for tc in msg.tool_calls:
                print(f"[Tool Call {tc.name}: {tc.arguments}]\n")
        elif isinstance(msg, ToolResultMessage):
            snippet = msg.content[:200] + ("..." if len(msg.content) > 200 else "")
            print(f"[Tool output {msg.tool_name}: {snippet.strip()}]\n")


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("MODEL")

    cwd = Path.cwd()

    context_files = discover_project_context(cwd)
    skills = discover_skills(cwd)
    dynamic_system_prompt: str = (
        system_prompt.strip()
        + format_project_context(context_files)
        + format_skills(skills)
    )

    provider = OpenAIProvider(api_key=api_key, base_url=base_url)
    tools = [
        create_bash_tool(),
        create_read_tool(),
        create_write_tool(),
        create_edit_tool(),
    ]

    session_manager = ChatSessionManager()
    session_id, storage = session_manager.new_session_storage()

    extension_runtime = ExtensionRuntime()
    extension_dir = cwd / ".mini-pi" / "extensions"
    extension_dir.mkdir(parents=True, exist_ok=True)

    await load_extensions_from_dir(extension_dir, extension_runtime)

    config = CodingSessionConfig(
        provider=provider,
        model=model,
        system=dynamic_system_prompt,
        tools=tools,
        storage=storage,
        auto_compact_threshold=50_000,
        extension_runtime=extension_runtime,
    )

    coding_session = await CodingSession.load(config)

    print(f"Mini Pi started with model '{model}'. Session: {session_id}.\n", flush=True)

    while True:
        user_input = input("user> ").strip()

        if not user_input:
            continue

        if user_input.lower() in ("exit",):
            print("\nGoodBye")
            break

        if user_input.startswith("/"):
            parts = user_input.lower().split(maxsplit=1)
            cmd = parts[0]
            arg = parts[1].strip() if len(parts) > 1 else None

            if cmd in ("/exit",):
                print("\nGoodBye")
                break

            if cmd in ("/clear",):
                session_id, storage = session_manager.new_session_storage()
                config.storage = storage
                coding_session = await CodingSession.load(config)
                clear_screen()
                print(f"\nStarting new session: {session_id}\n", flush=True)
                continue

            elif cmd == "/session":
                print(f"Active session: {session_id}", flush=True)
                continue

            elif cmd == "/resume":
                if not arg:
                    session_rows = session_manager.list_sessions()
                    print("\nAvaliable Sessions:")
                    for s in session_rows:
                        print(
                            f"- {s.updated_at.strftime('%m-%d %H:%M')} | {s.id}",
                            flush=True,
                        )

                    print("Use `/resume <id>` to switch\n")
                    continue

                matched = session_manager.get_session_storage(arg)
                if matched is None:
                    print(f"No session with '{arg}'", flush=True)
                    continue

                session_id, storage = matched
                config.storage = storage
                coding_session = await CodingSession.load(config)
                clear_screen()
                print(
                    f"\nResuming session: {session_id} with {len(coding_session.harness.messages)} messages\n",
                    flush=True,
                )
                print_session_history(coding_session.harness.messages)
                continue

        print("assistant> ", end="", flush=True)

        in_thinking = False

        try:
            async for event in coding_session.prompt(user_input):
                if isinstance(event, ThinkingDeltaEvent):
                    if not in_thinking:
                        print("|start_thinking|\n", end="", flush=True)
                        in_thinking = True

                    print(f"\033[90m{event.delta}\033[0m", end="", flush=True)
                elif in_thinking:
                    in_thinking = False
                    print("\n|end_thinking|\n\n", end="", flush=True)

                if isinstance(event, TextDeltaEvent):
                    print(event.delta, end="", flush=True)
                elif isinstance(event, ToolExecutionStartEvent):
                    print(
                        f"\n\n[Tool Call: {event.tool_name}({event.arguments})]\n",
                        flush=True,
                    )
                elif isinstance(event, ToolExecutionEndEvent):
                    snippet = event.result[:200] + (
                        "..." if len(event.result) > 200 else ""
                    )
                    print(
                        f"\n\n[Tool Output {event.tool_name}: {snippet.strip()}]\n",
                        flush=True,
                    )
                elif isinstance(event, AssistantErrorEvent):
                    print(f"\n[Error: {event.error}]\n", flush=True)

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[Interrupted by user]\n", flush=True)

        print("\n")


if __name__ == "__main__":
    load_dotenv()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodBye")
