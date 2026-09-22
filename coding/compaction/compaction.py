from agent.cancellation import CancellationSignal
from agent.events import DoneEvent
from agent.provider import ModelProvider
from ai.types import (
    AIModel,
    AssistantMessage,
    UserMessage,
)
from coding.compaction.prepare import serialize_messages_for_compaction
from coding.compaction.prompt import SUMMARIZATION_PROMPT, SUMMARIZATION_SYSTEM_PROMPT
from coding.messages import SessionMessage


async def generate_compaction_summary(
    provider: ModelProvider,
    model: AIModel,
    messages_to_summarize: list[SessionMessage],
    custom_instructions: str | None = None,
    previous_summary: str | None = None,
    signal: CancellationSignal | None = None,
) -> str:
    conversation_text = serialize_messages_for_compaction(messages_to_summarize)

    prompt: str = f"{SUMMARIZATION_PROMPT}\n"

    if previous_summary:
        prompt += f"<previous-summary>\n{previous_summary}\n</previous-summary>\n"

    prompt += f"<conversation>\n{conversation_text}\n</conversation>\n"

    if custom_instructions:
        prompt += f"\n\nAdditional Focus: {custom_instructions}"

    response: AssistantMessage | None = None

    async for event in provider.stream_response(
        model=model,
        system=SUMMARIZATION_SYSTEM_PROMPT,
        messages=[UserMessage(content=prompt)],
        tools=[],
        signal=signal,
    ):
        if isinstance(event, DoneEvent):
            response = event.message

    # TODO: why we are raising runtime error?
    if response is None:
        raise RuntimeError("Summarization returned no response")

    if response.stop_reason == "error":
        raise RuntimeError(
            f"Summarization failed: {response.error_message or 'unknown error'}"
        )

    if response.stop_reason == "aborted":
        raise RuntimeError("Summarization Cancelled")

    # TODO: We can drop initial messages
    if response.stop_reason == "length":
        raise RuntimeError("Summarization hit the output token limit")

    # TODO: retry to same llm not to call tools
    if response.tool_calls:
        raise RuntimeError("Summarization attempted to call tool")

    summary = response.content.strip()

    if not summary:
        raise RuntimeError("Compaction summarization returned an empty summary")

    return summary


# We can append the file operation happened across messages
# in summary generated from compaction request so LLM post compaction
# have immediate context of what files it has read or modified
def format_file_operations(messages: list[SessionMessage]):
    read: set[str] = set()
    modified: set[str] = set()

    for msg in messages:
        if not isinstance(msg, AssistantMessage):
            continue

        for tc in msg.tool_calls:
            path = tc.arguments.get("path")

            if not isinstance(path, str):
                continue

            if tc.name == "read":
                read.add(path)
            elif tc.name in ("write", "edit"):
                modified.add(path)

    read_only = "\n".join(sorted(read - modified))
    modified_files = "\n".join(sorted(modified))

    sections: list[str] = []

    if read_only:
        sections.append(f"<read-files>\n{read_only}\n</read-files>")

    if modified_files:
        sections.append(f"<modified-files>\n{modified_files}\n</modified-files>")

    return "\n\n".join(sections)
