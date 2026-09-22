from dataclasses import dataclass

from coding.messages import SessionMessage


@dataclass
class CompactionSettings:
    # Context window represent the total tokens model can process.
    # So if context window is 256K, and we send input tokens of 250K
    # then model can not generate more than 6K output tokens as limited by context window
    # reserver_tokens is minimum space left free in context window so when we call llm,
    # llm has enough space left in context window to generate its output
    # In nutshell, do compaction when
    # context_tokens (i.e current prompt tokens) > (context_window - reserve_tokens)
    reserve_tokens: int = 25_000
    # We can keep recent messages around this token budget
    # Basically we dont send those messages for compaction
    # M1 M2 M3 M4 M5 M6: if budget allow keep M5, M6
    # Compaction (M1, M2, M3, M4) = S1
    # Then post compaction: S1, M5, M6
    keep_recent_tokens: int = 20_000
    enabled: bool = (
        True  # Whether auto compaction is enabled or user explicitly manages the compaction
    )


@dataclass
class CompactionPreparation:
    first_kept_entry_id: str
    messages_to_summarize: list[
        SessionMessage
    ]  # TODO: it will not contain CompactionSummary message
    # Summary from the last compaction if exist
    previous_summary: str | None = None
