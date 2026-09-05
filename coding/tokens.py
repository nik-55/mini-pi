import math

from agent.messages import (
    AgentMessage,
    AssistantMessage,
    ToolResultMessage,
    UserMessage,
)

CHARS_PER_TOKEN = 4


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def estimate_message_tokens(message: AgentMessage) -> int:
    tokens = 0

    if isinstance(message, UserMessage):
        tokens += estimate_text_tokens(message.content)
    elif isinstance(message, AssistantMessage):
        tokens += estimate_text_tokens(message.content)
        # TODO: Thinking tokens ignored by provider in bw user messages
        for tool_call in message.tool_calls:
            tokens += estimate_text_tokens(tool_call.name) + estimate_text_tokens(
                str(tool_call.arguments)
            )

    elif isinstance(message, ToolResultMessage):
        tokens += estimate_text_tokens(message.tool_name)
        tokens += estimate_text_tokens(message.content)

    return tokens


def estimate_context_tokens(
    messages: list[AgentMessage],
):
    total = 0

    for msg in messages:
        total += estimate_message_tokens(msg)

    return total
