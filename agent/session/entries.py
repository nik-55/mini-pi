from enum import StrEnum
import time
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent.messages import AgentMessage


class SessionType(StrEnum):
    MESSAGE = "message"
    SESSION_INFO = "session_info"
    LEAF = "leaf"


def generate_session_entry_id() -> str:
    return uuid4().hex


def current_timestamp() -> float:
    return time.time()


class BaseSessionEntry(BaseModel):
    id: str = Field(default_factory=generate_session_entry_id)
    parent_id: str | None = None
    timestamp: float = Field(default_factory=current_timestamp)


class MessageEntry(BaseSessionEntry):
    type: Literal[SessionType.MESSAGE] = SessionType.MESSAGE
    message: AgentMessage


class SessionInfoEntry(BaseSessionEntry):
    type: Literal[SessionType.SESSION_INFO] = SessionType.SESSION_INFO
    created_at: float = Field(default_factory=current_timestamp)


class LeafEntry(BaseSessionEntry):
    type: Literal[SessionType.LEAF] = SessionType.LEAF
    entry_id: str | None = None


SessionEntry = Annotated[
    MessageEntry | LeafEntry | SessionInfoEntry, Field(discriminator="type")
]
