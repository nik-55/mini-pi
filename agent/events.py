from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from ai.types import (
    Message,
    AssistantMessage,
    AssistantMessageEvent,
    ToolResultMessage,
)

# Events: Agent Loop needs to broadcast state transitions in real time so different subscriber can act accordingly
#
# Suppose user send the prompt: "Read file foo.py and explain it"
# agent_start: Agent loop begins
#   message_start and message_end for the UserMessage ("Read file foo.py ...")
#   turn_start: Turn 1 begins
#       Prompt is send to LLM
#       message_start for AssistantMessage
#       message_update: LLM is streaming tokens
#       message_end: Full AssistantMessage containing tool calls
#       Tool executes: tool_execution_start -> tool_execution_end
#       message_start and message_end for ToolResultMessage
#   turn_end
#   turn_start: Turn 2 begins
#       tool result with message history feed to llm
#       message_start -> message_update (deltas) -> message_end for AssistantMessage
#       No tool calls
#   turn_end
# agent_end: No more tool calls and no queued messages
#
# Message Lifecycle
#   message_start: Initial notification that a message started
#   message_update: Streaming update for current message
#   message_end: Message is finalized
# Other than assistant message, other messages are always formed fully at once i.e no streaming
# so we emit message_start and message_end immediately


class AgentEventTypes(StrEnum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"

    TURN_START = "turn_start"
    TURN_END = "turn_end"

    MESSAGE_START = "message_start"
    MESSAGE_UPDATE = "message_update"
    MESSAGE_END = "message_end"

    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_EXECUTION_END = "tool_execution_end"


# Agent Loop Event


class AgentStartEvent(BaseModel):
    type: Literal[AgentEventTypes.AGENT_START] = AgentEventTypes.AGENT_START


class AgentEndEvent(BaseModel):
    type: Literal[AgentEventTypes.AGENT_END] = AgentEventTypes.AGENT_END
    messages: list[Message] = Field(default_factory=list)


class TurnStartEvent(BaseModel):
    type: Literal[AgentEventTypes.TURN_START] = AgentEventTypes.TURN_START


class TurnEndEvent(BaseModel):
    type: Literal[AgentEventTypes.TURN_END] = AgentEventTypes.TURN_END
    message: AssistantMessage
    tool_results: list[ToolResultMessage] = Field(default_factory=list)


class MessageStartEvent(BaseModel):
    type: Literal[AgentEventTypes.MESSAGE_START] = AgentEventTypes.MESSAGE_START
    message: Message


# Required only for assistant message as it streams
class MessageUpdateEvent(BaseModel):
    type: Literal[AgentEventTypes.MESSAGE_UPDATE] = AgentEventTypes.MESSAGE_UPDATE
    assistant_message_event: AssistantMessageEvent


class MessageEndEvent(BaseModel):
    type: Literal[AgentEventTypes.MESSAGE_END] = AgentEventTypes.MESSAGE_END
    message: Message


class ToolExecutionStartEvent(BaseModel):
    type: Literal[AgentEventTypes.TOOL_EXECUTION_START] = (
        AgentEventTypes.TOOL_EXECUTION_START
    )
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ToolExecutionEndEvent(BaseModel):
    type: Literal[AgentEventTypes.TOOL_EXECUTION_END] = (
        AgentEventTypes.TOOL_EXECUTION_END
    )
    tool_call_id: str
    tool_name: str
    result: str
    is_error: bool = False


AgentEvent = Annotated[
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionEndEvent,
    Field(discriminator="type"),
]
