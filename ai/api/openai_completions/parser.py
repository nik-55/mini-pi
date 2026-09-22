# Reference: https://github.com/openai/openai-python/blob/v3.13.0/src/openai/_streaming.py

import json
from typing import Any

from agent.events import (
    DoneEvent,
    AgentEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
)
from ai.types import AssistantMessage, StopReason, ToolCall, Usage


def _str_to_dict(text: str) -> dict | None:
    try:
        return json.loads(text)
    except Exception:
        return None


class ToolCallBuilder:
    def __init__(self):
        self.id: str = ""
        self.name: str = ""
        self.arguments_parts: list[str] = []

    def add_delta(self, delta: dict[str, Any]):
        call_id = delta.get("id", None)

        if isinstance(call_id, str):
            self.id = call_id

        function = delta.get("function", None)

        if not isinstance(function, dict):
            return

        name = function.get("name")
        if isinstance(name, str):
            self.name = name

        arguments = function.get("arguments")
        if isinstance(arguments, str):
            self.arguments_parts.append(arguments)

    def build(self, index: int) -> ToolCall:
        arguments_text = "".join(self.arguments_parts)
        arguments = _str_to_dict(arguments_text) if arguments_text else {}

        if arguments is None:
            arguments = {"_raw_arguments": arguments_text}

        tool_call_id = self.id or f"tool-call-{index}"

        return ToolCall(
            id=tool_call_id,
            name=self.name or tool_call_id,
            arguments=arguments,
        )


class ChatStreamParser:
    def __init__(self):
        self.content_parts: list[str] = []
        self.thinking_parts: list[str] = []
        self.tool_call_builders: dict[int, ToolCallBuilder] = {}
        self.finish_reason: str | None = None
        self.thinking_key: str | None = None
        self.usage: Usage | None = None

    def _first_choice(self, chunk: dict) -> dict | None:
        choices = chunk.get("choices", None)

        if not isinstance(choices, list) or len(choices) == 0:
            return

        choice = choices[0]

        if not isinstance(choice, dict):
            return

        return choice

    def build_assistant_message(
        self,
        stop_reason: StopReason | None = None,
        error_message: str | None = None,
    ) -> AssistantMessage:
        tool_calls: list[ToolCall] = [
            builder.build(index)
            for index, builder in sorted(
                self.tool_call_builders.items(), key=lambda x: x[0]
            )
        ]

        thinking = "".join(self.thinking_parts) or ""
        content = "".join(self.content_parts) or ""

        return AssistantMessage(
            content=content,
            thinking=thinking,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            error_message=error_message,
            thinking_signature=self.thinking_key,
            usage=self.usage,
        )

    def _map_finish_reason_to_stop_reason(
        self, finish_reason: str | None
    ) -> StopReason:
        if finish_reason == "tool_calls":
            return "tool_use"

        return finish_reason

    def feed(self, chunk: dict) -> list[AgentEvent]:
        # When include usage is True, choice can be empty
        # Extract usage before asserting on choice
        # usage chunk is emitted at end
        usage_dict = chunk.get("usage")

        if isinstance(usage_dict, dict):
            # TODO: fireworks emit different keys
            prompt_tokens = usage_dict.get("prompt_tokens") or 0
            completion_tokens = usage_dict.get("completion_tokens") or 0
            total_tokens = usage_dict.get("total_tokens") or 0
            prompt_details = usage_dict.get("prompt_tokens_details") or {}
            cached_tokens = prompt_details.get("cached_tokens", 0) or 0

            self.usage = Usage(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cache_read=cached_tokens,
                total_tokens=total_tokens,
            )

        # In stream error payloads
        if "error" in chunk and chunk["error"]:
            err = chunk["error"]
            msg = None
            if isinstance(err, dict):
                msg = err.get("message")

            msg = msg or str(err) or "Unknown error"

            raise RuntimeError(f"Stream error: {msg}")

        choice = self._first_choice(chunk)

        if choice is None:
            return []

        finish_reason = choice.get("finish_reason")
        if finish_reason:
            self.finish_reason = finish_reason

        delta = choice.get("delta", None)

        if not isinstance(delta, dict):
            return []

        events: list[AgentEvent] = []

        for field_name in (
            "reasoning_content",
            "reasoning",
            "thinking",
            "reasoning_text",
        ):
            thinking = delta.get(field_name)

            if isinstance(thinking, str) and thinking:
                self.thinking_parts.append(thinking)

                if self.thinking_key is None:
                    self.thinking_key = field_name

                events.append(ThinkingDeltaEvent(delta=thinking))
                break

        content = delta.get("content", None)

        if isinstance(content, str) and content:
            self.content_parts.append(content)
            events.append(TextDeltaEvent(delta=content))

        tool_call_deltas = delta.get("tool_calls", None)

        if isinstance(tool_call_deltas, list):
            tool_call_deltas = [t for t in tool_call_deltas if isinstance(t, dict)]

            for tool_call_delta in tool_call_deltas:
                index = int(tool_call_delta.get("index", 0))
                builder = self.tool_call_builders.setdefault(index, ToolCallBuilder())
                builder.add_delta(tool_call_delta)

        return events

    def finalize(self) -> DoneEvent:
        if self.finish_reason is None:
            raise RuntimeError("Stream ended without finish_reason")

        if self.finish_reason == "content_filter":
            raise RuntimeError("Provider finish_reason: content_filter")

        if self.finish_reason not in ("stop", "tool_calls", "length"):
            raise RuntimeError(f"Provider finish_reason: {self.finish_reason}")

        stop_reason = self._map_finish_reason_to_stop_reason(self.finish_reason)

        assistant_msg = self.build_assistant_message(
            stop_reason,
            error_message=None,
        )

        return DoneEvent(
            message=assistant_msg,
        )
