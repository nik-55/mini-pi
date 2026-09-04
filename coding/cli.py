import asyncio
import os

from dotenv import load_dotenv

from agent.events import (
    AssistantErrorEvent,
    TextDeltaEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from agent.loop import run_agent_loop
from agent.messages import AgentMessage, UserMessage
from ai.openai import OpenAIProvider
from coding.tools import create_read_tool, create_bash_tool

system_prompt = """
You are helpful assistant. You have access to user filesystem.
"""


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("MODEL")

    provider = OpenAIProvider(api_key=api_key, base_url=base_url)
    tools = [create_bash_tool(), create_read_tool()]

    messages: list[AgentMessage] = []

    print(f"Mini Pi started with model '{model}'. Type 'exit' to end.\n")

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

        messages.append(UserMessage(content=user_input))

        print("assistant> ", end="", flush=True)

        async for event in run_agent_loop(
            provider=provider,
            model=model,
            system=system_prompt,
            messages=messages,
            tools=tools,
        ):
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
