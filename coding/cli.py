import asyncio
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

from coding.command_factory import build_command_registry
from coding.commands import CommandRegistry, CommandResult
from coding.events import SessionEvent
from coding.extensions.types import ExtensionUIContext
from coding.session_factory import build_session_config
from coding.session import CodingSession
from coding.session_manager.manager import ChatSessionManager, list_sessions


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
    config = await build_session_config(
        chat_session_manager=ChatSessionManager.new_session()
    )

    # TODO: Should we set context UI directly by assigning?
    config.extension_runtime.context.ui = CliExtensionUI()
    coding_session = await CodingSession.load(config)

    command_registry: CommandRegistry = build_command_registry(
        extension_runtime=config.extension_runtime
    )

    print(
        f"Mini Pi started with model '{config.model.name}'. Session: {config.chat_session_manager.session_id}.\n",
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

    session_unsubscribe = coding_session.subscribe(print_event)

    while True:
        user_input = input("user> ").strip()

        if not user_input:
            continue

        command_result: CommandResult = command_registry.execute(text=user_input)

        if command_result.is_command:
            if command_result.message:
                print(f"\n{command_result.message}\n", flush=True)

            if command_result.action is None:
                continue

            if command_result.action.action == "exit":
                print("\nGoodBye")
                break

            if command_result.action.action == "clear":
                new_chat_session_manager = ChatSessionManager.new_session(
                    cwd=config.chat_session_manager.cwd
                )
                config.chat_session_manager = new_chat_session_manager
                session_unsubscribe()
                coding_session = await CodingSession.load(config)
                session_unsubscribe = coding_session.subscribe(print_event)
                clear_screen()
                print(
                    f"\nStarting new session: {config.chat_session_manager.session_id}\n",
                    flush=True,
                )
                continue

            if command_result.action.action == "session":
                print(
                    f"Active session: {config.chat_session_manager.session_id}",
                    flush=True,
                )
                continue

            if command_result.action.action == "resume":
                args = command_result.action.args

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

                new_chat_session_manager = ChatSessionManager.search_session(
                    args, cwd=config.chat_session_manager.cwd
                )
                if new_chat_session_manager is None:
                    print(f"No session with '{args}'", flush=True)
                    continue

                config.chat_session_manager = new_chat_session_manager
                session_unsubscribe()
                coding_session = await CodingSession.load(config)
                session_unsubscribe = coding_session.subscribe(print_event)
                clear_screen()
                print(
                    f"\nResuming session: {new_chat_session_manager.session_id} with {len(coding_session.harness.messages)} messages\n",
                    flush=True,
                )
                print_session_history(coding_session.harness.messages)
                continue

            if command_result.action.action == "compact":
                instructions = command_result.action.args or None

                await coding_session.compact(
                    custom_instructions=instructions,
                    reason="manual",
                )

                continue

        print("assistant> ", end="", flush=True)
        in_thinking = False

        try:
            await coding_session.prompt(user_input)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[Interrupted by user]\n", flush=True)

        print("\n")


if __name__ == "__main__":
    load_dotenv()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodBye")
