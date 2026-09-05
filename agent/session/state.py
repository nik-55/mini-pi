from pydantic import BaseModel

from agent.messages import AgentMessage
from agent.session.entries import MessageEntry, SessionEntry, SessionInfoEntry
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

        for entry in branch:
            if isinstance(entry, MessageEntry):
                messages.append(entry.message)
            elif isinstance(entry, SessionInfoEntry):
                session_info = entry

        return cls(
            messages=messages,
            session_info=session_info,
            active_leaf_id=leaf_id,
        )
