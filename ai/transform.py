from agent.messages import (
    AgentMessage,
    AssistantMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


def transform_messages(messages: list[AgentMessage]) -> list[AgentMessage]:
    result: list[AgentMessage] = []
    pending_tool_calls: list[ToolCall] = []
    existing_tool_result_ids: set[str] = set()

    def insert_synthetic_tool_results():
        nonlocal pending_tool_calls, existing_tool_result_ids

        for tc in pending_tool_calls:
            if tc.id not in existing_tool_result_ids:
                result.append(
                    ToolResultMessage(
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                        content="No result provided",
                        is_error=True,
                    )
                )

        pending_tool_calls = []
        existing_tool_result_ids = set()

    # Make sure all previous tool results are inserted before
    # appending either a User Message or new Assistant Msg or continue the conversation
    for msg in messages:
        if isinstance(msg, AssistantMessage):
            # GEMINI: Why it is placed at this location??
            insert_synthetic_tool_results()

            if msg.stop_reason in ("error", "aborted"):
                continue

            if len(msg.tool_calls) > 0:
                pending_tool_calls = list(msg.tool_calls)
                existing_tool_result_ids = set()

            result.append(msg)
        elif isinstance(msg, ToolResultMessage):
            existing_tool_result_ids.add(msg.tool_call_id)
            result.append(msg)
        elif isinstance(msg, UserMessage):
            insert_synthetic_tool_results()
            result.append(msg)

    insert_synthetic_tool_results()

    return result
