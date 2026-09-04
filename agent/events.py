from pydantic import BaseModel

from agent.messages import AssistantMessage


class TextDeltaEvent(BaseModel):
    delta: str


class AssistantDoneEvent(BaseModel):
    message: AssistantMessage


class AssistantErrorEvent(BaseModel):
    error: str


ProviderDeltaEvent = TextDeltaEvent | AssistantDoneEvent | AssistantErrorEvent
