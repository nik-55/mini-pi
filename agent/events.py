from typing import Any

from pydantic import BaseModel

from agent.messages import AssistantMessage


class TextDeltaEvent(BaseModel):
    delta: str


class ThinkingDeltaEvent(BaseModel):
    delta: str


class AssistantDoneEvent(BaseModel):
    message: AssistantMessage


class AssistantErrorEvent(BaseModel):
    error: str


class ToolExecutionStartEvent(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ToolExecutionEndEvent(BaseModel):
    tool_call_id: str
    tool_name: str
    result: str
    is_error: bool = False


AgentEvent = (
    TextDeltaEvent
    | ThinkingDeltaEvent
    | AssistantDoneEvent
    | AssistantErrorEvent
    | ToolExecutionStartEvent
    | ToolExecutionEndEvent
)
