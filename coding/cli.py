import asyncio
from collections.abc import Callable
import sys

from dotenv import load_dotenv

from ai.types import (
    Message,
    AssistantMessage,
    MessageType,
    ToolResultMessage,
    UserMessage,
    EventTypes,
)
from agent.events import AgentEventTypes

from coding.commands import BUILTIN_SLASH_COMMANDS, parse_command
from coding.events import SessionEvent
from coding.extensions.types import ExtensionUIContext
from coding.session_factory import build_session_config
from coding.session import CodingSession
from coding.session_manager.manager import list_sessions
from coding.session_runtime import CodingSessionRuntime


def clear_screen():
    sys.stdout.write("\033[2J\033[3J\033[H")
    sys.stdout.flush()


def print_session_history(messages: list[Message]):
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


class CliExtensionUI(ExtensionUIContext):
    async def select(self, title: str, options: list[str]) -> str | None:
        print(f"\n{title}", flush=True)

        for idx, opt in enumerate(options, start=1):
            print(f" {idx}. {opt}", flush=True)

        try:
            choice = input(f"Select [1-{len(options)}]: ").strip()
            choice = choice.strip()

            if not choice:
                return

            if choice.isdigit():
                num = int(choice)

                if 1 <= num <= len(options):
                    return options[num - 1]

            return
        except (KeyboardInterrupt, EOFError):
            return

    def notify(self, message: str, level: str = "info") -> None:
        print(f"\n[{level.upper()}] {message}", flush=True)


async def main():
    config = await build_session_config()

    # TODO: Should we set context UI directly by assigning?
    config.extension_runtime.context.ui = CliExtensionUI()
    session_runtime = await CodingSessionRuntime.create(config)

    print(
        f"Mini Pi started with model '{session_runtime.session.config.model.name}'. Session: {session_runtime.session.chat_session_manager.session_id}.\n",
        flush=True,
    )

    in_thinking = False

    def print_event(event: SessionEvent) -> None:
        nonlocal in_thinking

        if event.type == AgentEventTypes.MESSAGE_UPDATE:
            delta_event = event.assistant_message_event

            if delta_event.type == EventTypes.THINKING_DELTA:
                if not in_thinking:
                    print("|start_thinking|\n", end="", flush=True)
                    in_thinking = True

                print(f"\033[90m{delta_event.delta}\033[0m", end="", flush=True)
            elif in_thinking:
                in_thinking = False
                print("\n|end_thinking|\n\n", end="", flush=True)

            if delta_event.type == EventTypes.TEXT_DELTA:
                print(delta_event.delta, end="", flush=True)

        elif event.type == AgentEventTypes.TOOL_EXECUTION_START:
            print(
                f"\n\n[Tool Call: {event.tool_name}({event.arguments})]\n",
                flush=True,
            )
        elif event.type == AgentEventTypes.TOOL_EXECUTION_END:
            snippet = event.result[:200] + ("..." if len(event.result) > 200 else "")
            print(
                f"\n\n[Tool Output {event.tool_name}: {snippet.strip()}]\n",
                flush=True,
            )
        elif event.type == AgentEventTypes.MESSAGE_END:
            if in_thinking:
                in_thinking = False

            if (
                event.message.role == MessageType.ASSISTANT
                and event.message.stop_reason in ("error", "aborted")
            ):
                print(
                    f"\n[{event.message.stop_reason.upper()}]: {event.message.error_message}",
                    flush=True,
                )
        elif event.type == "compaction_start":
            print(f"\n[Compacting ({event.reason})...]", flush=True)
        elif event.type == "compaction_end":
            if event.error_message:
                print(f"\n[Compaction failed: {event.error_message}]", flush=True)
            else:
                print(f"\n[{event.result}]", flush=True)

    session_unsubscribe: Callable[[], None] | None = None

    def rebind_session(session: CodingSession) -> None:
        nonlocal session_unsubscribe

        if session_unsubscribe is not None:
            session_unsubscribe()

        session_unsubscribe = session.subscribe(print_event)

    session_runtime.set_rebind_session(rebind_session)
    rebind_session(session_runtime.session)

    while True:
        user_input = input("user> ").strip()

        if not user_input:
            continue

        name, args = parse_command(user_input)

        if name == "exit":
            print("\nGoodBye")
            break

        if name == "clear":
            await session_runtime.new_session()
            clear_screen()
            print(
                f"\nStarting new session: {session_runtime.session.chat_session_manager.session_id}\n",
                flush=True,
            )
            continue

        if name == "session":
            print(
                f"Active session: {session_runtime.session.chat_session_manager.session_id}",
                flush=True,
            )
            continue

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
                continue

            try:
                await session_runtime.switch_session(args)
            except ValueError as err:
                print(err, flush=True)
                continue

            clear_screen()
            print(
                f"\nResuming session: {session_runtime.session.chat_session_manager.session_id} with {len(session_runtime.session.harness.messages)} messages\n",
                flush=True,
            )
            print_session_history(session_runtime.session.harness.messages)
            continue

        if name == "compact":
            instructions = args or None

            await session_runtime.session.compact(
                custom_instructions=instructions,
                reason="manual",
            )

            continue

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
            continue

        print("assistant> ", end="", flush=True)
        in_thinking = False

        try:
            await session_runtime.session.prompt(user_input)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[Interrupted by user]\n", flush=True)

        print("\n")


if __name__ == "__main__":
    load_dotenv()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodBye")
