from collections.abc import AsyncIterator

from agent.events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AgentEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from agent.messages import AgentMessage, AssistantMessage, ToolResultMessage
from agent.provider import ModelProvider
from agent.tools import AgentTool


async def run_agent_loop(
    provider: ModelProvider,
    model: str,
    system: str,
    messages: list[AgentMessage],
    tools: list[AgentTool],
    max_turns: int = 40,
) -> AsyncIterator[AgentEvent]:
    tool_map = {t.name: t for t in tools}

    for _ in range(max_turns):
        assistant_message: AssistantMessage | None = None

        stream = provider.stream_response(
            model=model,
            system=system,
            messages=messages,
            tools=tools,
        )

        async for event in stream:
            if isinstance(event, TextDeltaEvent):
                yield event
            elif isinstance(event, ThinkingDeltaEvent):
                yield event
            elif isinstance(event, AssistantDoneEvent):
                assistant_message = event.message
                yield event
            elif isinstance(event, AssistantErrorEvent):
                yield event
                return

        if assistant_message is None:
            yield AssistantErrorEvent(error="No assistant message received")
            return

        messages.append(assistant_message)

        if not assistant_message.tool_calls:
            return

        for tool_call in assistant_message.tool_calls:
            yield ToolExecutionStartEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
            )

            tool = tool_map.get(tool_call.name)

            if tool is None:
                content = f"Error: tool '{tool_call.name}' not found"
                is_error = True
            else:
                try:
                    content = await tool.execute(tool_call.arguments)
                    is_error = False
                except Exception as exc:
                    content = f"Error executing tool '{tool_call.name}': {exc}"
                    is_error = True

            tool_result_message = ToolResultMessage(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                content=content,
                is_error=is_error,
            )

            messages.append(tool_result_message)

            yield ToolExecutionEndEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=content,
                is_error=is_error,
            )
