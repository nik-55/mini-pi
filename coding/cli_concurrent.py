import asyncio
from collections.abc import Callable
import os

from dotenv import load_dotenv
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.mouse_events import MouseEventType
from prompt_toolkit.widgets import TextArea

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
from coding.tools import (
    create_edit_tool,
    create_read_tool,
    create_bash_tool,
    create_write_tool,
)
from coding.session import CodingSessionConfig, CodingSession
from coding.chat_session_manager import ChatSessionManager

system_prompt = """
You are helpful assistant. You have access to user filesystem.
"""


def format_session_history(messages: list[AgentMessage]) -> str:
    lines = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            lines.append(f"user> {msg.content}\n")
        elif isinstance(msg, AssistantMessage):
            lines.append(f"assistant> ")
            if msg.thinking:
                lines.append(f"|start_thinking|\n{msg.thinking}\n")
            if msg.content:
                lines.append(f"{msg.content}\n")

            for tc in msg.tool_calls:
                lines.append(f"[Tool Call {tc.name}: {tc.arguments}]\n")
        elif isinstance(msg, ToolResultMessage):
            snippet = msg.content[:200] + ("..." if len(msg.content) > 200 else "")
            lines.append(f"[Tool output {msg.tool_name}: {snippet.strip()}]\n")

    return "\n".join(lines)


async def run_loop(
    coding_session: CodingSession,
    user_input: str,
    append_output: Callable,
):
    append_output("assistant> ")
    in_thinking = False

    try:
        async for event in coding_session.prompt(user_input):
            if isinstance(event, ThinkingDeltaEvent):
                if not in_thinking:
                    append_output("|start_thinking|\n")
                    in_thinking = True

                append_output(f"{event.delta}")
            elif in_thinking:
                in_thinking = False
                append_output("\n|end_thinking|\n\n")

            if isinstance(event, TextDeltaEvent):
                append_output(event.delta)
            elif isinstance(event, ToolExecutionStartEvent):
                append_output(f"\n[Tool Call: {event.tool_name}({event.arguments})]\n")
            elif isinstance(event, ToolExecutionEndEvent):
                snippet = event.result[:200] + (
                    "..." if len(event.result) > 200 else ""
                )
                append_output(f"\n[Tool Output {event.tool_name}: {snippet.strip()}]\n")
            elif isinstance(event, AssistantErrorEvent):
                append_output(f"\n[Error: {event.error}]\n")

    except (KeyboardInterrupt, asyncio.CancelledError):
        append_output("\n[Interrupted by user]\n")

    append_output("\n\n")


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("MODEL")

    provider = OpenAIProvider(api_key=api_key, base_url=base_url)
    tools = [
        create_bash_tool(),
        create_read_tool(),
        create_write_tool(),
        create_edit_tool(),
    ]

    session_manager = ChatSessionManager()
    session_id, storage = session_manager.new_session_storage()

    config = CodingSessionConfig(
        provider=provider,
        model=model,
        system=system_prompt,
        tools=tools,
        storage=storage,
        auto_compact_threshold=50_000,
    )

    coding_session = await CodingSession.load(config)

    initial_text = f"Mini Pi started with model '{model}'. Session: {session_id}.\n\n"
    output_box = TextArea(
        text=initial_text,
        focusable=False,
        scrollbar=True,
        wrap_lines=True,
    )
    divider = Window(height=1, char="-")
    input_box = TextArea(
        height=1,
        prompt=[("bold fg:ansicyan", "user> ")],
        multiline=False,
        wrap_lines=False,
    )

    layout = Layout(
        HSplit([output_box, divider, input_box]),
        focused_element=input_box,
    )

    kb = KeyBindings()

    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        mouse_support=True,
    )

    def _mouse_scroll(mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            output_box.buffer.cursor_up(count=3)
            return
        elif mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            output_box.buffer.cursor_down(count=3)
            return
        return NotImplemented

    output_box.window._mouse_handler = _mouse_scroll

    active_task: asyncio.Task | None = None

    def append_output(text: str):
        output_box.text += text
        output_box.buffer.cursor_position = len(output_box.text)

    async def reload_session():
        nonlocal coding_session
        coding_session = await CodingSession.load(config)

    @kb.add("enter")
    def _on_enter(event):
        nonlocal active_task

        user_input = input_box.text.strip()

        input_box.text = ""

        if not user_input:
            return

        # user_input_thread = asyncio.to_thread(input, "user> ")
        # user_input_thread = session.prompt_async("user> ")

        # Await for input from user
        # user_input = (await user_input_thread).strip()

        if user_input.startswith("/"):
            parts = user_input.lower().split(maxsplit=1)
            cmd = parts[0]
            arg = parts[1].strip() if len(parts) > 1 else None

            if user_input.lower() in ("/exit"):
                event.app.exit()
                return

            if cmd in ("/clear",):
                session_id, storage = session_manager.new_session_storage()
                config.storage = storage
                asyncio.create_task(reload_session())
                output_box.text = f"\nStarting new session: {session_id}\n"
                output_box.buffer.cursor_position = len(output_box.text)
                return

            elif cmd == "/session":
                append_output(f"Active session: {session_id}")
                return

            elif cmd == "/resume":
                if not arg:
                    session_rows = session_manager.list_sessions()
                    append_output("\nAvaliable Sessions:")
                    for s in session_rows:
                        append_output(
                            f"- {s.updated_at.strftime('%m-%d %H:%M')} | {s.id}"
                        )

                    append_output("Use `/resume <id>` to switch\n")
                    return

                matched = session_manager.get_session_storage(arg)
                if matched is None:
                    append_output(f"No session with '{arg}'")
                    return

                session_id, storage = matched
                config.storage = storage
                asyncio.create_task(reload_session())

                output_box.text = f"\nResuming session: {session_id} with {len(coding_session.harness.messages)} messages\n"
                output_box.buffer.cursor_position = len(output_box.text)
                session_history_text = format_session_history(
                    coding_session.harness.messages
                )
                append_output(session_history_text)
                return

        if active_task and not active_task.done():
            return

        append_output(f"user> {user_input}\n\n")
        active_task = asyncio.create_task(
            run_loop(
                coding_session,
                user_input,
                append_output,
            )
        )

    @kb.add("c-c")
    def _on_ctrl_c(event):
        nonlocal active_task
        if active_task and not active_task.done():
            coding_session.cancel()
        else:
            event.app.exit()

    await app.run_async()


if __name__ == "__main__":
    load_dotenv()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodBye")
