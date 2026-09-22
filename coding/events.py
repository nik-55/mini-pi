from typing import Literal

from pydantic import BaseModel

from agent.events import AgentEvent

CompactionReason = Literal["manual", "threshold", "overflow"]


class CompactionStartEvent(BaseModel):
    type: Literal["compaction_start"] = "compaction_start"
    reason: CompactionReason


class CompactionEndEvent(BaseModel):
    type: Literal["compaction_end"] = "compaction_end"
    result: str | None = None
    error_message: str | None = None


CompactionEvent = CompactionStartEvent | CompactionEndEvent
SessionEvent = AgentEvent | CompactionEvent
