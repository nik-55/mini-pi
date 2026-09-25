from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter

from ai.types import Message


class SessionType(StrEnum):
    MESSAGE = "message"
    COMPACTION = "compaction"
    HEADER = "header"

    # SESSION_METADATA = "session_metadata"
    # MODEL_CHANGE = "model_change"
    # THINKING_LEVEL_CHANGE = "thinking_level_change"


def generate_session_entry_id() -> str:
    return uuid4().hex[:8]


# Store time in utc and when showing to user, we can convert to their local timezone
def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseEntry(BaseModel):
    type: SessionType
    id: str = Field(default_factory=generate_session_entry_id)
    timestamp: str = Field(default_factory=current_timestamp)


class SessionHeader(BaseEntry):
    type: Literal[SessionType.HEADER] = SessionType.HEADER
    cwd: str


class BaseSessionEntry(BaseEntry):
    parent_id: str | None = None


class MessageEntry(BaseSessionEntry):
    type: Literal[SessionType.MESSAGE] = SessionType.MESSAGE
    message: Message


# class ModelChangeEntry(BaseSessionEntry):
#     type: Literal[SessionType.MODEL_CHANGE] = SessionType.MODEL_CHANGE
#     model_ref: str


# class ThinkingLevelChangeEntry(BaseSessionEntry):
#     type: Literal[SessionType.THINKING_LEVEL_CHANGE] = SessionType.THINKING_LEVEL_CHANGE
#     thinking_level: ThinkingLevel


# class SessionMetaDataEntry(BaseSessionEntry):
#     type: Literal[SessionType.SESSION_METADATA] = SessionType.SESSION_METADATA
#     created_at: str = Field(default_factory=current_timestamp)


class CompactionEntry(BaseSessionEntry):
    type: Literal[SessionType.COMPACTION] = SessionType.COMPACTION
    summary: str
    first_kept_entry_id: str


SessionEntry = Annotated[
    SessionHeader
    | MessageEntry
    | CompactionEntry,
    Field(discriminator="type"),
]

session_entry_adapter: TypeAdapter[SessionEntry] = TypeAdapter(SessionEntry)


class SessionEntryError(ValueError):
    pass


def entry_to_json_line(entry: SessionEntry) -> str:
    return session_entry_adapter.dump_json(entry).decode() + "\n"


def entry_from_json_line(line: str) -> SessionEntry | None:
    if not line.strip():
        return

    try:
        return session_entry_adapter.validate_json(line)
    except Exception as exc:
        raise SessionEntryError(f"Invalid session entry: {exc}")
