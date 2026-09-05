from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel

from agent.events import AgentEvent
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

    def append_message(self, message: AgentMessage) -> None:
        self.messages.append(message)

    async def prompt(self, content: str) -> AsyncIterator[AgentEvent]:
        self.append_message(UserMessage(content=content))
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
            yield event
