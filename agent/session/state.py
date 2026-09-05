from pydantic import BaseModel, Field

from agent.messages import AgentMessage, UserMessage
from agent.session.entries import (
    MessageEntry,
    SessionEntry,
    SessionInfoEntry,
    CompactionEntry,
)
from agent.session.tree import branch_by_leaf_id


def _apply_compaction(
    message_rows: list[tuple[str, AgentMessage]],
    compaction_entry: CompactionEntry,
) -> list[tuple[str, AgentMessage]]:
    replaced_ids = set(compaction_entry.replaces_entry_ids)
    retained: list[tuple[str, AgentMessage]] = []
    summary_msg = UserMessage(
        content=f"Previous conversation summary: \n{compaction_entry.summary}"
    )

    is_summary_inserted = False

    for entry_id, message in message_rows:
        if entry_id not in replaced_ids:
            retained.append((entry_id, message))
            continue

        if not is_summary_inserted:
            retained.append((compaction_entry.id, summary_msg))
            is_summary_inserted = True

    if not is_summary_inserted:
        retained.append((compaction_entry.id, summary_msg))

    return retained


class SessionState(BaseModel):
    messages: list[AgentMessage]
    session_info: SessionInfoEntry | None = None
    active_leaf_id: str | None = None
    context_entry_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_entries(
        cls,
        entries: list[SessionEntry],
        leaf_id: str | None = None,
    ) -> "SessionState":
        branch = branch_by_leaf_id(entries, leaf_id) if leaf_id is not None else entries

        message_rows: list[tuple[str, AgentMessage]] = []
        session_info: SessionInfoEntry | None = None

        for entry in branch:
            if isinstance(entry, MessageEntry):
                message_rows.append((entry.id, entry.message))
            elif isinstance(entry, CompactionEntry):
                message_rows = _apply_compaction(message_rows, entry)
            elif isinstance(entry, SessionInfoEntry):
                session_info = entry

        messages = [msg for _, msg in message_rows]
        context_entry_ids = [entry_id for entry_id, _ in message_rows]

        return cls(
            messages=messages,
            session_info=session_info,
            active_leaf_id=leaf_id,
            context_entry_ids=context_entry_ids,
        )
