from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
import inspect
from typing import Any, Optional

from agent.events import AgentEvent, MessageEndEvent
from agent.loop import run_agent_loop
from agent.messages import AgentMessage, UserMessage
from agent.provider import ModelProvider
from agent.tools import AgentTool


@dataclass
class AgentHarnessConfig:
    provider: ModelProvider
    model: str
    system: str
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int = 40


class AgentHarness:
    def __init__(
        self,
        config: AgentHarnessConfig,
        messages: Optional[list[AgentMessage]] = None,
    ):
        self.messages = messages or []
        self.config = config
        self._listeners: list[Callable[[AgentEvent], Any]] = []

    def append_message(self, message: AgentMessage) -> None:
        self.messages.append(message)

    def subscribe(self, listener: Callable[[AgentEvent], Any]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    async def _notify(self, event: AgentEvent):
        snapshot_listeners = list(self._listeners)

        for listener in snapshot_listeners:
            result = listener(event)

            if inspect.isawaitable(result):
                await result

    async def prompt(self, content: str) -> AsyncIterator[AgentEvent]:
        user_message = UserMessage(content=content)
        self.append_message(message=user_message)
        event = MessageEndEvent(message=user_message)
        await self._notify(event)
        yield event

        async for event in self.continue_():
            yield event

    async def continue_(self) -> AsyncIterator[AgentEvent]:
        async for event in run_agent_loop(
            provider=self.config.provider,
            model=self.config.model,
            system=self.config.system,
            messages=self.messages,
            tools=self.config.tools,
            max_turns=self.config.max_turns,
        ):
            await self._notify(event)
            yield event
