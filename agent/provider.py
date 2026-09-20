from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from agent.cancellation import CancellationSignal
from agent.events import AgentEvent
from agent.tools import AgentTool
from ai.types import AIModel, AgentMessage


class ModelProvider(ABC):
    @abstractmethod
    def stream_response(
        self,
        *,
        model: AIModel,
        system: str,
        messages: list[AgentMessage],
        tools: list[AgentTool],
        signal: CancellationSignal | None = None,
    ) -> AsyncIterator[AgentEvent]:
        pass
