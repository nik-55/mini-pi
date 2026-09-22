import math

from ai.types import (
    AssistantMessage,
    ToolResultMessage,
    UserMessage,
)

from coding.messages import CompactionSummaryMessage, SessionMessage

# Heuristics based estimation

CHARS_PER_TOKEN = 4


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def estimate_message_tokens(message: SessionMessage) -> int:
    tokens = 0

    if isinstance(message, UserMessage):
        tokens += estimate_text_tokens(message.content)
    elif isinstance(message, AssistantMessage):
        tokens += estimate_text_tokens(message.content)
        # TODO: Provider may ignore the thinking tokens between user messages
        # even if we send back thinking tokens in API
        for tool_call in message.tool_calls:
            tokens += estimate_text_tokens(tool_call.name) + estimate_text_tokens(
                str(tool_call.arguments)
            )

    elif isinstance(message, ToolResultMessage):
        tokens += estimate_text_tokens(message.tool_name)
        tokens += estimate_text_tokens(message.content)

    elif isinstance(message, CompactionSummaryMessage):
        tokens += estimate_text_tokens(message.summary)

    return tokens


# Usage based token extraction
# Usage is helpful only when either total_tokens > 0 or (input_token > 0 and output_tokens > 0)
def extract_usage_tokens(msg: AssistantMessage) -> int | None:
    if msg.stop_reason in ("error", "aborted") or msg.usage is None:
        return

    usage = msg.usage

    if usage.total_tokens > 0:
        return usage.total_tokens

    if usage.input_tokens > 0 and usage.output_tokens > 0:
        return usage.input_tokens + usage.output_tokens

    return


# Estimate the tokens using usage wherever available
# and for rest use heuristics based estimation
def estimate_context_tokens(messages: list[SessionMessage]) -> int:
    last_usage_tokens: int | None = None
    last_valid_usage_index: int | None = None

    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], AssistantMessage):
            usage_tokens = extract_usage_tokens(messages[i])

            if usage_tokens is not None:
                last_usage_tokens = usage_tokens
                last_valid_usage_index = i
                break

    if last_valid_usage_index is None:
        return sum(estimate_message_tokens(m) for m in messages)

    # Estimate the tokens for which usage not available
    trailing_tokens = sum(
        estimate_message_tokens(messages[i])
        for i in range(last_valid_usage_index + 1, len(messages))
    )

    return last_usage_tokens + trailing_tokens
