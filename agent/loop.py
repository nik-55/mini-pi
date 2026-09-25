from collections.abc import AsyncIterator, Callable

from agent.types import AgentMessage
from ai.cancellation import CancellationSignal
from ai.types import (
    Context,
    StreamOptions,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    DoneEvent,
    AIModel,
    Message,
    AssistantMessage,
    ToolResultMessage,
    UserMessage,
)
from agent.events import (
    AgentEvent,
    AgentStartEvent,
    AgentEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    MessageEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionEndEvent,
    TurnStartEvent,
    TurnEndEvent,
)
from ai.provider import StreamFunction
from ai.validation import validate_tool_arguments
from agent.tools import AgentTool


async def run_agent_loop[CustomMessage](
    stream_fn: StreamFunction,
    model: AIModel,
    system: str,
    messages: list[AgentMessage[CustomMessage]],
    tools: list[AgentTool],
    signal: CancellationSignal | None = None,
    get_steering_messages: Callable[[], tuple[UserMessage, ...]] = None,
    get_followup_messages: Callable[[], tuple[UserMessage, ...]] = None,
    # Deliberately set to large number so agent can run for long but limit for how long till we have proper testing
    max_turns: int = 1000,
    convert_message_to_llm_compatible: Callable[
        [list[AgentMessage[CustomMessage]]], list[Message]
    ] = None,
) -> AsyncIterator[AgentEvent]:
    tool_map = {t.name: t for t in tools}
    # messages: entire session history
    # new_message_start_index: messages added during this agent run speciafically (i.e from agent_start to agent_end)
    new_message_start_index = len(messages)

    pending_queued_messages = tuple()

    yield AgentStartEvent()

    while True:
        is_assistant_done = False
        turn = 0

        while (not is_assistant_done) or len(pending_queued_messages) > 0:
            turn += 1
            yield TurnStartEvent()

            if turn > max_turns or (signal is not None and signal.is_cancelled()):
                assistant_message = AssistantMessage(
                    stop_reason="aborted",
                    error_message=(
                        "Operation cancelled"
                        if turn < max_turns
                        else "Max turn reached"
                    ),
                )
                messages.append(assistant_message)
                yield MessageStartEvent(message=assistant_message)
                yield MessageEndEvent(message=assistant_message)

                yield TurnEndEvent(message=assistant_message, tool_results=[])
                yield AgentEndEvent(messages=messages[new_message_start_index:])
                return

            for msg in pending_queued_messages:
                messages.append(msg)
                yield MessageStartEvent(message=msg)
                yield MessageEndEvent(message=msg)

            pending_queued_messages = tuple()

            assistant_message: AssistantMessage | None = None

            yield MessageStartEvent(message=AssistantMessage())

            stream = stream_fn(
                model,
                Context(
                    system=system,
                    messages=(
                        convert_message_to_llm_compatible(messages)
                        if convert_message_to_llm_compatible
                        else messages
                    ),
                    tools=tools,
                ),
                StreamOptions(
                    signal=signal,
                ),
            )

            async for event in stream:
                if signal is not None and signal.is_cancelled():
                    assistant_message = AssistantMessage(
                        stop_reason="aborted",
                        error_message="Operation cancelled",
                    )
                    break

                if isinstance(event, (TextDeltaEvent, ThinkingDeltaEvent)):
                    yield MessageUpdateEvent(assistant_message_event=event)
                elif isinstance(event, DoneEvent):
                    assistant_message = event.message

            if assistant_message is None:
                assistant_message = AssistantMessage(
                    stop_reason="error",
                    error_message="No assistant message received",
                )

            messages.append(assistant_message)
            yield MessageEndEvent(message=assistant_message)

            if assistant_message.stop_reason in ("error", "aborted"):
                yield TurnEndEvent(message=assistant_message, tool_results=[])
                yield AgentEndEvent(messages=messages[new_message_start_index:])
                return

            is_assistant_done = (
                True if len(assistant_message.tool_calls) == 0 else False
            )

            is_truncated = assistant_message.stop_reason == "length"
            tool_result_message_start_index = len(messages)

            for tool_call in assistant_message.tool_calls:
                yield ToolExecutionStartEvent(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                )

                if signal is not None and signal.is_cancelled():
                    content = "Operation cancelled"
                    is_error = True
                elif is_truncated:
                    content = (
                        f"Tool call '{tool_call.name}' was not executed: the response hit the output token limit, "
                        "so its arguments may be truncated. Re-issue the tool call with complete arguments."
                    )
                    is_error = True
                else:
                    tool = tool_map.get(tool_call.name)

                    if tool is None:
                        content = f"Error: tool '{tool_call.name}' not found"
                        is_error = True
                    else:
                        try:
                            validate_tool_arguments(
                                tool.parameters,
                                tool_call.arguments,
                            )
                            content = await tool.execute(
                                tool_call.arguments, signal=signal
                            )
                            is_error = False
                        except (Exception,) as exc:
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

                yield MessageStartEvent(message=tool_result_message)
                yield MessageEndEvent(message=tool_result_message)

            yield TurnEndEvent(
                message=assistant_message,
                tool_results=messages[tool_result_message_start_index:],
            )
            pending_queued_messages = (
                get_steering_messages() if get_steering_messages else tuple()
            )

        pending_queued_messages = (
            get_followup_messages() if get_followup_messages else tuple()
        )

        if len(pending_queued_messages) == 0:
            break

    yield AgentEndEvent(messages=messages[new_message_start_index:])
