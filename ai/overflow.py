# Provider give stop_reason when llm hit max_tokens before closing naturally
# However if the input tokens itself cross the context window, provider throw 400 error
# with context overflow error
# 400 can be due to bad request as well
# We can use overflow patterns to check if error is overflow error

# TODO: Though fireworks dont throw context overflow it seems
# https://docs.fireworks.ai/tools-sdks/openai-compatibility#differences

import re

from ai.types import AssistantMessage

OVERFLOW_PATTERNS = [
    # OPENAI Compatible overflow error
    re.compile(r"context[_ ]length[_ ]exceeded", re.IGNORECASE),
]


def is_context_overflow(message: AssistantMessage) -> bool:
    if message.stop_reason != "error" or not message.error_message:
        return False

    return any(pattern.search(message.error_message) for pattern in OVERFLOW_PATTERNS)
