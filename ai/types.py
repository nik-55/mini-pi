from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# Messages


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


StopReason = Literal["stop", "length", "tool_use", "error", "aborted"]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    total_tokens: int = 0


class AssistantMessage(BaseModel):
    role: Literal[MessageType.ASSISTANT] = MessageType.ASSISTANT
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    thinking: str = ""
    # The actual field name provider used to stream thinking tokens
    # reasoning or reasoning_content or thinking or reasoning_text
    thinking_signature: str | None = None
    stop_reason: StopReason | None = None
    error_message: str | None = None
    usage: Usage | None = None


class ToolResultMessage(BaseModel):
    role: Literal[MessageType.TOOLRESULT] = MessageType.TOOLRESULT
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


AgentMessage = Annotated[
    UserMessage | AssistantMessage | ToolResultMessage, Field(discriminator="role")
]

# AI Model

# Off means if model have reasoning capability but we can turn it off
ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "max"]


# Compatibility
class OpenAICompletionsComp(BaseModel):
    supports_usage_in_streaming: bool = (
        True  # Whether sending stream_options: {"include_usage": true} supported or not
    )
    # The actual field name required by provider for max_tokens for eg max_completion_tokens
    max_tokens_field: str | None = None


class AIModel(BaseModel):
    id: str
    name: str
    api: str = "openai-completions"
    provider: str
    base_url: str
    reasoning: bool  # Is model have reasoning capability?
    thinking_level_map: dict[ThinkingLevel, str | None] = Field(
        default_factory=dict
    )  # Mapping of thinking levels to model specific keys
    context_window: int  # Maximum total token capacity (input prompt tokens + output token generated)
    max_tokens: int  # maximum output token model can generate in single call
    compat: OpenAICompletionsComp | None = None
