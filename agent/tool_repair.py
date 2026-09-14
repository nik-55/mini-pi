from agent.messages import AgentMessage, AssistantMessage, ToolResultMessage


def get_tool_result_repairs(messages: list[AgentMessage]) -> list[ToolResultMessage]:
    tool_result_ids_existing = {
        m.tool_call_id for m in messages if isinstance(m, ToolResultMessage)
    }

    last_assistant_msg = None

    for m in reversed(messages):
        if isinstance(m, AssistantMessage):
            last_assistant_msg = m
            break

    if last_assistant_msg is None:
        return []

    tool_result_repairs: list[ToolResultMessage] = []

    for tc in last_assistant_msg.tool_calls:
        if tc.id not in tool_result_ids_existing:
            tool_result_repairs.append(
                ToolResultMessage(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=f"Tool call is either interrupted or never executed",
                    is_error=True,
                )
            )

    return tool_result_repairs
