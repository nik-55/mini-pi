from agent.events import DoneEvent, TextDeltaEvent
from ai.types import (
    AIModel,
    AgentMessage,
    AssistantMessage,
    ToolResultMessage,
    UserMessage,
)
from agent.provider import ModelProvider
from coding.tokens import estimate_message_tokens

# At least keep this much recent tokens
DEFAULT_KEEP_RECENT_TOKENS = 6_000

SUMMARIZATION_SYSTEM_PROMPT = """
You are context summarization assistant. Your task is to read conversation between user and AI coding assistant, then produce a concise, structured summary following the exact format specified.
Do not continue the conversation. Do not respond to any questions in the conversation. Do not call tools, tools are not available. Do not try to explore more to gather more information. Your only task is to output the structured summary.
"""

SUMMARIZATION_PROMPT = """
Use this exact format

## Goal

## Constraints & Preferences

## Progress

### Done

### In Progress

### Blocked

### Key Decisions

## Next Steps

## Critical Context
- [Any file paths, function names, error messages, or context needed to continue]

"""


def find_compaction_cut(
    messages: list[AgentMessage], keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS
) -> int | None:
    if len(messages) < 2:
        return

    accumulated_tokens = 0
    candidate_index: int | None = None

    for i in range(len(messages) - 1, 1, -1):
        accumulated_tokens += estimate_message_tokens(messages[i])

        if accumulated_tokens >= keep_recent_tokens:
            candidate_index = i
            break

    if candidate_index is None:
        return

    if isinstance(messages[candidate_index], UserMessage):
        return candidate_index

    cut: int | None = None

    # Search forward from candidate_index+1 to find user message
    for i in range(candidate_index + 1, len(messages)):
        if isinstance(messages[i], UserMessage):
            cut = i
            break

    if cut is None and candidate_index > 1:
        for i in range(candidate_index - 1, 1, -1):
            if isinstance(messages[i], UserMessage):
                cut = i
                break

    return cut


def serialize_messages_for_compaction(messages: list[AgentMessage]) -> str:
    lines: list[str] = []

    for msg in messages:
        if isinstance(msg, UserMessage):
            lines.append(f"<message role='user'>\n{msg.content}\n</message>")
        elif isinstance(msg, AssistantMessage):
            content = (msg.content or "").strip()

            if msg.tool_calls:
                tool_lines = [f" - {tc.name}: {tc.arguments}" for tc in msg.tool_calls]

                content = (
                    f"{content}\n<tool_calls>\n"
                    + "\n".join(tool_lines)
                    + "\n</tool_calls>"
                )

            lines.append(f"<message role='assistant'>\n{content}\n</message>")
        elif isinstance(msg, ToolResultMessage):
            status = "failed" if msg.is_error else "ok"
            lines.append(
                f"<message role='tool' name='{msg.tool_name}' status={status}>\n{msg.content}\n</message>"
            )

    return "\n".join(lines)


async def generate_compaction_summary(
    provider: ModelProvider,
    model: AIModel,
    messages_to_summarize: list[AgentMessage],
    custom_instructions: str | None = None,
) -> str:
    conversation_text = serialize_messages_for_compaction(messages_to_summarize)

    prompt = f"<conversation>\n{conversation_text}\n</conversation>\n\n{SUMMARIZATION_PROMPT}"

    if custom_instructions:
        prompt += f"\n\nAdditional Focus: {custom_instructions}"

    text_parts: list[str] = []
    final_text: str | None = None

    async for event in provider.stream_response(
        model=model,
        system=SUMMARIZATION_SYSTEM_PROMPT,
        messages=[UserMessage(content=prompt)],
        tools=[],
    ):
        if isinstance(event, TextDeltaEvent):
            text_parts.append(event.delta)
        elif isinstance(event, DoneEvent):
            final_text = event.message.content

    summary = final_text if final_text is not None else "".join(text_parts).strip()

    if not summary:
        raise RuntimeError("Compaction summarization returned an empty summary")

    return summary
