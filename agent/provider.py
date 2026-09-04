import abc
from collections.abc import AsyncIterator

from agent.events import AgentEvent
from agent.messages import AgentMessage
from agent.tools import AgentTool


class ModelProvider(abc.ABC):
    def stream_response(
        self,
        *,
        model: str,
        system: str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
    ) -> AsyncIterator[AgentEvent]:
        pass
