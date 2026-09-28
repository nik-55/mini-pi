import asyncio
from collections.abc import Callable
import sys

from ai.types import (
    Message,
    AssistantMessage,
    MessageType,
    ToolResultMessage,
    UserMessage,
    EventTypes,
)
from agent.events import AgentEventTypes

from coding.auth import set_api_key_to_auth
from coding.commands import BUILTIN_SLASH_COMMANDS, parse_command
from coding.events import SessionEvent
from coding.modes.cli.extension_ui import CliExtensionUI
from coding.session import CodingSession
from coding.session_manager.manager import list_sessions
from coding.session_runtime import CodingSessionRuntime

# Terminal color codes
DIM = "\033[90m"
RESET = "\033[0m"


def clear_screen():
    sys.stdout.write("\033[2J\033[3J\033[H")
    sys.stdout.flush()


def print_session_history(messages: list[Message]):
    for msg in messages:
        if isinstance(msg, UserMessage):
            print(f"\nuser> {msg.content}")
        elif isinstance(msg, AssistantMessage):
            print("\nassistant>")
            if msg.thinking:
                print(f"{DIM}[thinking]\n{msg.thinking}\n[thinking end]{RESET}\n")
            if msg.content:
                print(msg.content)

            for tc in msg.tool_calls:
                print(f"\n[tool call] {tc.name}({tc.arguments})")
        elif isinstance(msg, ToolResultMessage):
            snippet = msg.content[:200] + ("..." if len(msg.content) > 200 else "")
            print(f"\n[tool output] {msg.tool_name}: {snippet.strip()}")


# Return exit status (return True to exit)
async def handle_input(user_input: str, session_runtime: CodingSessionRuntime) -> bool:
    name, args = parse_command(user_input)

    # Abort
    if name == "exit":
        print("\nGoodBye")
        return True

    # Screen
    if name == "clear":
        await session_runtime.new_session()
        clear_screen()
        print(
            f"\nStarting new session: {session_runtime.session.chat_session_manager.session_id}\n",
            flush=True,
        )
        return False

    # Session
    if name == "session":
        print(
            f"Active session: {session_runtime.session.chat_session_manager.session_id}",
            flush=True,
        )
        return False

    if name == "resume":
        if not args:
            session_rows = list_sessions()
            print("\nAvaliable Sessions:")
            for s in session_rows:
                print(
                    f"- {s.updated_at.strftime('%m-%d %H:%M')} | {s.id}",
                    flush=True,
                )

            print("Use `/resume <id>` to switch\n")
            return False

        try:
            await session_runtime.switch_session(args)
        except ValueError as err:
            print(err, flush=True)
            return False

        clear_screen()
        print(
            f"\nResuming session: {session_runtime.session.chat_session_manager.session_id} with {len(session_runtime.session.harness.messages)} messages\n",
            flush=True,
        )
        print_session_history(session_runtime.session.harness.messages)
        return False

    # Compact
    if name == "compact":
        instructions = args or None

        await session_runtime.session.compact(
            custom_instructions=instructions,
            reason="manual",
        )

        return False

    # Auth
    if name == "login":
        parts = args.split()

        if len(parts) < 2:
            print("Usage: /login <provider> <key>", flush=True)
            return False

        provider, key = parts[0], parts[1]
        set_api_key_to_auth(provider, key)

        print(f"Saved API key for {provider}", flush=True)
        return False

    # Help
    if name == "help":
        lines = []

        if len(BUILTIN_SLASH_COMMANDS) > 0:
            lines.append("Available built in commands")

        for c in BUILTIN_SLASH_COMMANDS:
            hint = f" {c.argument_hint}" if c.argument_hint else ""
            lines.append(f" /{c.name}{hint} - {c.description}")

        extension_runtime = session_runtime.session.config.extension_runtime

        if extension_runtime is not None:
            builtin_names = {c.name for c in BUILTIN_SLASH_COMMANDS}
            extension_commands = extension_runtime.get_all_commands()

            if len(extension_commands) > 0:
                lines.append("Available extension commands")

            for c in extension_commands:
                if c.name not in builtin_names:
                    lines.append(f" /{c.name} - {c.description}")

        print("\n" + "\n".join(lines) + "\n", flush=True)
        return False

    await session_runtime.session.prompt(user_input)
    return False


async def run_cli_mode(session_runtime: CodingSessionRuntime) -> None:
    session_unsubscribe: Callable[[], None] | None = None

    def rebind_session(new_session: CodingSession) -> None:
        nonlocal session_unsubscribe

        if session_unsubscribe is not None:
            session_unsubscribe()

        if new_session.config.extension_runtime is not None:
            # TODO: Should we set context UI directly by assigning?
            new_session.config.extension_runtime.context.ui = CliExtensionUI()

        session_unsubscribe = new_session.subscribe(print_event)

    print(
        f"Mini Pi started with model '{session_runtime.session.config.model.name}'. Session: {session_runtime.session.chat_session_manager.session_id}.\n",
        flush=True,
    )

    in_thinking = False

    def print_event(event: SessionEvent) -> None:
        nonlocal in_thinking

        if event.type == AgentEventTypes.MESSAGE_START:
            if event.message.role == MessageType.ASSISTANT:
                in_thinking = False
                print("\nassistant>")

        if event.type == AgentEventTypes.MESSAGE_UPDATE:
            delta_event = event.assistant_message_event

            if delta_event.type == EventTypes.THINKING_DELTA:
                if not in_thinking:
                    print(f"{DIM}[thinking]{RESET}")
                    in_thinking = True

                print(f"{DIM}{delta_event.delta}{RESET}", end="", flush=True)
            elif in_thinking:
                in_thinking = False
                print(f"\n{DIM}[thinking end]{RESET}\n")

            if delta_event.type == EventTypes.TEXT_DELTA:
                print(delta_event.delta, end="", flush=True)

        elif event.type == AgentEventTypes.TOOL_EXECUTION_START:
            print(f"\n\n[tool call] {event.tool_name}({event.arguments})")
        elif event.type == AgentEventTypes.TOOL_EXECUTION_END:
            snippet = event.result[:200] + ("..." if len(event.result) > 200 else "")
            print(f"\n[tool output] {event.tool_name}: {snippet.strip()}")
        elif event.type == AgentEventTypes.MESSAGE_END:
            if in_thinking:
                in_thinking = False

            if (
                event.message.role == MessageType.ASSISTANT
                and event.message.stop_reason in ("error", "aborted")
            ):
                print(
                    f"\n\n[{event.message.stop_reason}] {event.message.error_message}"
                )
        elif event.type == "compaction_start":
            print(f"\n[compaction] started ({event.reason})")
        elif event.type == "compaction_end":
            if event.error_message:
                print(f"\n[compaction] failed: {event.error_message}")
            else:
                print(f"\n[compaction] {event.result}")

    session_runtime.set_rebind_session(rebind_session)
    rebind_session(session_runtime.session)

    while True:
        user_input = input("user> ").strip()

        if not user_input:
            continue

        in_thinking = False
        try:
            exit_status = await handle_input(user_input, session_runtime)

            if exit_status:
                break
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[Interrupted by user]\n", flush=True)
            continue

        print("\n")
