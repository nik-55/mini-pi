from typing import Any
import json

from agent.messages import (
    AgentMessage,
    AssistantMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from agent.tools import AgentTool

# OpenAI represent Chat completion API /v1/chat/completions


def tool_to_openai(tool: AgentTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _tool_call_to_openai(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.name,
            "arguments": json.dumps(tool_call.arguments),
        },
    }


def message_to_openai(message: AgentMessage) -> dict[str, Any]:
    if isinstance(message, UserMessage):
        return {
            "role": "user",
            "content": message.content,
        }

    if isinstance(message, AssistantMessage):
        msg = {"role": "assistant", "content": message.content}

        if len(message.tool_calls) > 0:
            msg["tool_calls"] = [
                _tool_call_to_openai(tool_call) for tool_call in message.tool_calls
            ]

        return msg

    if isinstance(message, ToolResultMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "name": message.tool_name,
            "content": message.content,
        }


def build_chat_payload(
    model: str,
    system: str,
    messages: list[AgentMessage],
    tools: list[AgentTool],
) -> dict[str, Any]:
    payload = {
        "messages": [{"role": "system", "content": system}]
        + [message_to_openai(m) for m in messages],
        "model": model,
        "stream": True,
    }

    if len(tools) > 0:
        payload["tools"] = [tool_to_openai(t) for t in tools]

    return payload
