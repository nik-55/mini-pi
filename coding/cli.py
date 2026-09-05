import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from agent.events import (
    AssistantErrorEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from ai.openai import OpenAIProvider
from coding.tools import (
    create_edit_tool,
    create_read_tool,
    create_bash_tool,
    create_write_tool,
)
from coding.session import CodingSessionConfig, CodingSession
from coding.storage import JsonlSessionStorage

system_prompt = """
You are helpful assistant. You have access to user filesystem.
"""


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

    session_file = Path.cwd() / ".mini-pi" / "sessions" / "default.jsonl"
    storage = JsonlSessionStorage(path=session_file)

    config = CodingSessionConfig(
        provider=provider,
        model=model,
        system=system_prompt,
        tools=tools,
        storage=storage,
    )

    session = await CodingSession.load(config)

    print(f"Mini Pi started with model '{model}'. Type 'exit' to end.\n")

    if session.harness.messages:
        print(f"Resumed previous session ({len(session.harness.messages)} messages)")

    while True:
        try:
            user_input = input("user> ").strip()
        except (Exception, KeyboardInterrupt):
            print("\nGoodBye")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit",):
            print("\nGoodBye")
            break

        print("assistant> ", end="", flush=True)

        in_thinking = False

        async for event in session.prompt(user_input):
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

        print("\n")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
