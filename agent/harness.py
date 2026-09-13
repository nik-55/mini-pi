from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
import inspect
from typing import Any, Optional

from agent.cancellation import CancellationSignal
from agent.events import AgentEvent, MessageEndEvent
from agent.loop import run_agent_loop
from agent.messages import AgentMessage, UserMessage
from agent.provider import ModelProvider
from agent.queue import MessageQueueHandler
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
        self._cancellation_signal: CancellationSignal | None = None
        self.is_running: bool = False
        self.msg_queue_when_running = MessageQueueHandler()

    def append_message(self, message: AgentMessage) -> None:
        self.messages.append(message)

    def replace_messages(self, messages: list[AgentMessage]) -> None:
        self.messages = list(messages)

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
        if self.is_running:
            raise RuntimeError(
                "Agent is already running, use msg_queue_when_running to queue messages"
            )

        user_message = UserMessage(content=content)
        self.append_message(message=user_message)
        event = MessageEndEvent(message=user_message)
        await self._notify(event)
        yield event

        async for event in self._continue():
            yield event

    async def _continue(self) -> AsyncIterator[AgentEvent]:
        signal = CancellationSignal()
        self._cancellation_signal = signal

        self.is_running = True

        try:
            async for event in run_agent_loop(
                provider=self.config.provider,
                model=self.config.model,
                system=self.config.system,
                messages=self.messages,
                tools=self.config.tools,
                max_turns=self.config.max_turns,
                signal=signal,
                get_steering_messages=self.msg_queue_when_running.drain_steering,
                get_followup_messages=self.msg_queue_when_running.drain_follow_up,
            ):
                await self._notify(event)
                yield event
        finally:
            if self._cancellation_signal is signal:
                self._cancellation_signal = None

            self.is_running = False

    def cancel(self):
        if self._cancellation_signal is not None:
            self._cancellation_signal.cancel()
