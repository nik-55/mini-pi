from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
import inspect
from typing import Any, Optional

from agent.types import AgentMessage
from ai.cancellation import CancellationSignal
from agent.events import (
    AgentEndEvent,
    AgentEvent,
    MessageEndEvent,
    MessageStartEvent,
    TurnEndEvent,
)
from agent.loop import run_agent_loop
from ai.types import AIModel, Message, AssistantMessage, UserMessage
from ai.provider import StreamFunction
from agent.queue import MessageQueueHandler
from agent.tools import AgentTool


@dataclass
class AgentHarnessConfig[CustomMessage]:
    stream_fn: StreamFunction
    model: AIModel
    system: str
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int = 40
    convert_message_to_llm_compatible: (
        Callable[[list[AgentMessage[CustomMessage]]], list[Message]] | None
    ) = None


class AgentHarness[CustomMessage]:
    def __init__(
        self,
        config: AgentHarnessConfig[CustomMessage],
        messages: Optional[list[AgentMessage[CustomMessage]]] = None,
    ):
        self.messages = messages or []
        self.config = config
        self._listeners: list[Callable[[AgentEvent], Any]] = []
        self._cancellation_signal: CancellationSignal | None = None
        self.is_running: bool = False
        self.msg_queue_when_running = MessageQueueHandler()

    def append_message(self, message: AgentMessage[CustomMessage]) -> None:
        self.messages.append(message)

    def replace_messages(self, messages: list[AgentMessage[CustomMessage]]) -> None:
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

        start_event = MessageStartEvent(message=user_message)
        await self._notify(start_event)
        yield start_event

        end_event = MessageEndEvent(message=user_message)
        await self._notify(end_event)
        yield end_event

        async for event in self._continue():
            yield event

    async def _continue(self) -> AsyncIterator[AgentEvent]:
        signal = CancellationSignal()
        self._cancellation_signal = signal

        self.is_running = True

        try:
            async for event in run_agent_loop(
                stream_fn=self.config.stream_fn,
                model=self.config.model,
                system=self.config.system,
                messages=self.messages,
                tools=self.config.tools,
                max_turns=self.config.max_turns,
                signal=signal,
                get_steering_messages=self.msg_queue_when_running.drain_steering,
                get_followup_messages=self.msg_queue_when_running.drain_follow_up,
                convert_message_to_llm_compatible=self.config.convert_message_to_llm_compatible,
            ):
                await self._notify(event)
                yield event
        except Exception as err:
            last_msg = self.messages[-1] if self.messages else None
            if not (
                isinstance(last_msg, AssistantMessage)
                and last_msg.stop_reason in ("error", "aborted")
            ):
                failure_message = AssistantMessage(
                    stop_reason="error",
                    error_message=str(err),
                )
                self.append_message(failure_message)

                for ev in (
                    MessageStartEvent(message=failure_message),
                    MessageEndEvent(message=failure_message),
                    TurnEndEvent(message=failure_message, tool_results=[]),
                    AgentEndEvent(messages=[failure_message]),
                ):
                    await self._notify(ev)
                    yield ev
        finally:
            if self._cancellation_signal is signal:
                self._cancellation_signal = None

            self.is_running = False

    def cancel(self):
        if self._cancellation_signal is not None:
            self._cancellation_signal.cancel()
