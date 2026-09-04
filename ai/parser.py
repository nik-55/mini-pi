import json
from typing import Any

from agent.events import (
    AssistantDoneEvent,
    AgentEvent,
    TextDeltaEvent,
)
from agent.messages import AssistantMessage, ToolCall


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
        self.tool_call_builders: dict[int, ToolCallBuilder] = {}

    def _first_choice(self, chunk: dict) -> dict | None:
        choices = chunk.get("choices", None)

        if not isinstance(choices, list) or len(choices) == 0:
            return

        choice = choices[0]

        if not isinstance(choice, dict):
            return

        return choice

    def feed(self, chunk: dict) -> list[AgentEvent]:
        choice = self._first_choice(chunk)

        if choice is None:
            return []

        delta = choice.get("delta", None)

        if not isinstance(delta, dict):
            return []

        events: list[AgentEvent] = []

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

    def finalize(self) -> AssistantDoneEvent:
        tool_calls: list[ToolCall] = [
            builder.build(index)
            for index, builder in sorted(
                self.tool_call_builders.items(), key=lambda x: x[0]
            )
        ]

        content = "".join(self.content_parts) or ""

        return AssistantDoneEvent(
            message=AssistantMessage(
                content=content,
                tool_calls=tool_calls,
            )
        )
