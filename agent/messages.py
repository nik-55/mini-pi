from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class MessageType(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOLRESULT = "tool_result"


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class UserMessage(BaseModel):
    role: Literal[MessageType.USER] = MessageType.USER
    content: str


class AssistantMessage(BaseModel):
    role: Literal[MessageType.ASSISTANT] = MessageType.ASSISTANT
    content: str = ""
    tool_calls: list[ToolCall] = []


class ToolResultMessage(BaseModel):
    role: Literal[MessageType.TOOLRESULT] = MessageType.TOOLRESULT
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


AgentMessage = Annotated[
    UserMessage | AssistantMessage | ToolResultMessage, Field(discriminator="role")
]
