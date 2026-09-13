from pydantic import BaseModel

from agent.messages import AgentMessage, UserMessage
from agent.session.entries import (
    MessageEntry,
    SessionEntry,
    SessionInfoEntry,
    CompactionEntry,
)
from agent.session.tree import branch_by_leaf_id


class SessionState(BaseModel):
    messages: list[AgentMessage]
    session_info: SessionInfoEntry | None = None
    active_leaf_id: str | None = None

    @classmethod
    def from_entries(
        cls,
        entries: list[SessionEntry],
        leaf_id: str | None = None,
    ) -> "SessionState":
        branch = branch_by_leaf_id(entries, leaf_id) if leaf_id is not None else entries

        messages: list[AgentMessage] = []
        session_info: SessionInfoEntry | None = None
        latest_compaction_index: int | None = None

        # Traverse branch backwards
        for i in range(len(branch) - 1, -1, -1):
            entry = branch[i]

            if isinstance(entry, SessionInfoEntry):
                session_info = entry
            elif isinstance(entry, CompactionEntry) and latest_compaction_index is None:
                latest_compaction_index = i

        if latest_compaction_index is not None:
            compaction_entry: CompactionEntry = branch[latest_compaction_index]
            summary_msg = UserMessage(
                content=f"Previously conversation summary: \n{compaction_entry.summary}"
            )
            messages.append(summary_msg)
            messages.extend(compaction_entry.retained_tail)
            tail_entries = branch[latest_compaction_index + 1 :]
        else:
            tail_entries = branch

        for entry in tail_entries:
            if isinstance(entry, MessageEntry):
                messages.append(entry.message)

        return cls(
            messages=messages,
            session_info=session_info,
            active_leaf_id=leaf_id,
        )
