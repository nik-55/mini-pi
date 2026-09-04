from pydantic import BaseModel

from agent.messages import AssistantMessage


class TextDeltaEvent(BaseModel):
    delta: str


class ToolCallDeltaEvent(BaseModel):
    index: int
    id: str | None = None
    name: str | None = None
    arguments_delta: str = ""


class AssistantDoneEvent(BaseModel):
    message: AssistantMessage


class AssistantErrorEvent(BaseModel):
    error: str


ProviderDelta = (
    TextDeltaEvent | ToolCallDeltaEvent | AssistantDoneEvent | AssistantErrorEvent
)
