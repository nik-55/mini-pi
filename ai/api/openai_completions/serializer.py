from typing import Any
import json

from ai.types import (
    AIModel,
    Message,
    AssistantMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
    Tool,
)
from ai.transform import transform_messages


def tool_to_openai(tool: Tool) -> dict[str, Any]:
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


def message_to_openai(message: Message) -> dict[str, Any]:
    if isinstance(message, UserMessage):
        return {
            "role": "user",
            "content": message.content,
        }

    if isinstance(message, AssistantMessage):
        msg = {"role": "assistant", "content": message.content}

        if message.thinking:
            thinking_key = message.thinking_signature or "reasoning_content"
            msg[thinking_key] = message.thinking

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
    model: AIModel,
    system: str,
    messages: list[Message],
    tools: list[Tool],
) -> dict[str, Any]:
    messages = transform_messages(messages)
    payload = {
        "messages": [{"role": "system", "content": system}]
        + [message_to_openai(m) for m in messages],
        "model": model.id,
        "stream": True,
    }

    if len(tools) > 0:
        payload["tools"] = [tool_to_openai(t) for t in tools]

    # Include usage unless disabled by compat
    supports_usage_in_streaming = True

    if model.compat:
        supports_usage_in_streaming = model.compat.supports_usage_in_streaming

    if supports_usage_in_streaming:
        payload["stream_options"] = {"include_usage": True}

    return payload
