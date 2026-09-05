from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from pydantic import BaseModel

from agent.events import AgentEvent, AssistantDoneEvent, ToolExecutionEndEvent
from agent.harness import AgentHarness, AgentHarnessConfig
from agent.messages import AgentMessage, ToolResultMessage, UserMessage
from agent.provider import ModelProvider
from agent.session.entries import (
    LeafEntry,
    MessageEntry,
    SessionEntry,
    SessionInfoEntry,
)
from agent.session.state import SessionState
from agent.session.storage import SessionStorage
from agent.tools import AgentTool


@dataclass
class CodingSessionConfig:
    provider: ModelProvider
    model: str
    system: str
    storage: SessionStorage
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int = 40


def _latest_leaf_entry(entries: list[SessionEntry]) -> LeafEntry | None:
    for entry in reversed(entries):
        if isinstance(entry, LeafEntry):
            return entry

    return


class CodingSession:
    def __init__(
        self,
        config: CodingSessionConfig,
        harness: AgentHarness,
        last_parent_id: str | None = None,
    ):
        self.config = config
        self.harness = harness
        self.last_parent_id = last_parent_id

    @classmethod
    async def load(cls, config: CodingSessionConfig) -> "CodingSession":
        entries = await config.storage.read_all()
        last_parent_id: str | None = None

        if not entries:
            info = SessionInfoEntry()
            await config.storage.append(info)
            entries = [info]

        latest_leaf = _latest_leaf_entry(entries)
        leaf_id = latest_leaf.entry_id if latest_leaf else None
        last_parent_id = leaf_id if leaf_id else entries[-1].id

        state = SessionState.from_entries(entries, leaf_id=leaf_id)

        harness_config = AgentHarnessConfig(
            provider=config.provider,
            model=config.model,
            system=config.system,
            tools=config.tools,
            max_turns=config.max_turns,
        )

        harness = AgentHarness(config=harness_config, messages=state.messages)

        return cls(
            config=config,
            harness=harness,
            last_parent_id=last_parent_id,
        )

    async def prompt(self, content: str) -> AsyncIterator[AgentEvent]:
        start_index = len(self.harness.messages)

        async for event in self.harness.prompt(content):
            yield event

        new_messages = self.harness.messages[start_index:]

        for msg in new_messages:
            entry = MessageEntry(parent_id=self.last_parent_id, message=msg)
            await self.config.storage.append(entry)
            self.last_parent_id = entry.id

        if self.last_parent_id is not None:
            leaf = LeafEntry(
                parent_id=self.last_parent_id, entry_id=self.last_parent_id
            )
            await self.config.storage.append(leaf)
