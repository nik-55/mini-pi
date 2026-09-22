from ai.types import (
    AssistantMessage,
    ToolResultMessage,
    UserMessage,
)
from coding.compaction.tokens import estimate_message_tokens
from coding.compaction.types import CompactionPreparation, CompactionSettings
from coding.messages import SessionMessage
from coding.session_manager.entries import CompactionEntry, SessionEntry
from coding.session_manager.traversal import entry_to_message


def check_compaction_threshold(
    context_tokens: int,
    context_window: int,
    settings: CompactionSettings,
) -> bool:
    return context_tokens > (context_window - settings.reserve_tokens)


# When we compact we keep tail of messages (i.e recent messages) that survive compaction
# The CompactionSummary message is send to llm as UserMessage
# Cut point is the first entry after CompactionSummary message
# Now a UserMessage can only be followed by an assistant message or another UserMessage
# A ToolResult message can not be cut point as tool result require the tool calls that produce it
# to be there when send to providers
# There can be multiple compaction happened in single session
# resulting in multiple CompactionEntry or CompactionSummary message
# Should we consider CompactionSummary as valid cut point as it is UserMessage?
# - When we send compaction request we will send previous summary
# (i.e summary from last CompactionSummary message, call it s1)
# in <previous-summary> tag so when newer summary generated (call it s2), it will be derived
# from context of s1 already
# - By definition of cut point, it is first entry after compaction, so it means
# if we keep CompactionSummary as cut point, post compaction: S2, S1
# and hence we endup with s2 newer summary followed by older summary
# Hence we will not treat CompactionSummary as valid cut point


# Check whether message is cut point or not
def is_cut_point_message(message: SessionMessage) -> bool:
    return isinstance(message, (UserMessage, AssistantMessage))


# Why entries not messages?
# - CompactionEntry requires first_kept_entry_id i.e we will need entry id
# - Also the way messages in session constructed is basically:
# Take summary from latest compaction if available and then keep summary plus tail messages and newer messages
# so cut index on messages and then tracing it to entry id without carrying entries in session can be tricky
# For simplicity we can do compaction on entries
# TODO why we cant use messages?


# Walk backwards on entries and accumulate the tokens
# Keep track of last cut point found
# When accumulated tokens become greater than budget of recent tokens
# and if cut point exist return cut point
# otherwise there is no valid cut point yet so keep moving backward until found
# TODO:
# Limitation:
# - What if last messages are tool result which are verbose. Since no valid cut point exist until last assistant message that produce them,
# the following algo will cut on that assistant message leaving verbose tool result in context.
# There is no mechanism here to say dont keep any recent messages
# Tool result message cant be cut point but if they come as expense of context window why to keep those recent messages.
# - keep recent tokens is used as approx budget and there is no threshold check of kept tail of messages
def find_cut_point(
    entries: list[SessionEntry],
    keep_recent_tokens: int,
) -> int | None:
    accumulated_tokens = 0
    last_cut_point: int | None = None

    for i in range(len(entries) - 1, -1, -1):
        message = entry_to_message(entries[i])

        if message is None:
            continue

        if is_cut_point_message(message):
            last_cut_point = i

        accumulated_tokens += estimate_message_tokens(message)

        if accumulated_tokens >= keep_recent_tokens and last_cut_point is not None:
            return last_cut_point

    return


def prepare_compaction(
    messages_entries: list[SessionEntry],
    settings: CompactionSettings,
) -> CompactionPreparation | None:
    previous_summary: str | None = None

    # If compaction entry is present in messages_entries, it should occur
    # at first index as tail entry will come after them
    # (because this is messages_entries not branch entries)
    if messages_entries and isinstance(messages_entries[0], CompactionEntry):
        previous_summary = messages_entries[0].summary

    # Meaning of None is basically
    # Either a valid cut point does not exist or accumulated token
    # never cross keep recent tokens
    # In both the cases dont do compaction

    # Ignore the first CompactionEntry as previous summary handle it
    candidates = messages_entries[1:] if previous_summary else messages_entries

    cut = find_cut_point(candidates, keep_recent_tokens=settings.keep_recent_tokens)

    if cut is None:
        return

    messages_to_summarize: list[SessionMessage] = []

    # cut index is first entry that is kept in tail
    for entry in candidates[:cut]:
        message = entry_to_message(entry)

        # message can not be None as messages_entries represent messages
        if message is None:
            raise ValueError(f"{entry} do not have corresponding message")

        messages_to_summarize.append(message)

    if not messages_to_summarize:
        return

    return CompactionPreparation(
        first_kept_entry_id=candidates[cut].id,
        messages_to_summarize=messages_to_summarize,
        previous_summary=previous_summary,
    )


# Compaction runs when context is near the window and the messages_to_summarize construct most of that
# context. Generally we use same model (as Session use) for compaction, so our compaction request is also
# near context window. We can handle this senario by cutting tool result output to TOOL_RESULT_MAX_CHARS.
# Tool result mostly responsible for bulk of context and matter least for a summary.

TOOL_RESULT_MAX_CHARS = 2000


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    dropped = len(text) - max_chars
    return f"{text[:max_chars]}\n\n[... {dropped} more characters truncated]"


def serialize_messages_for_compaction(messages: list[SessionMessage]) -> str:
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
            body = truncate_text(msg.content, TOOL_RESULT_MAX_CHARS)
            lines.append(
                f"<message role='tool' name='{msg.tool_name}' status={status}>\n{body}\n</message>"
            )

    return "\n".join(lines)
