from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from agent.events import AgentEvent, MessageEndEvent
from agent.harness import AgentHarness, AgentHarnessConfig
from agent.messages import AgentMessage, UserMessage
from agent.provider import ModelProvider
from agent.session.entries import (
    CompactionEntry,
    LeafEntry,
    MessageEntry,
    SessionEntry,
    SessionInfoEntry,
)
from agent.session.state import SessionState
from agent.session.storage import SessionStorage
from agent.tools import AgentTool
from coding.compaction import find_compaction_cut, generate_compaction_summary
from coding.extensions.api import InputHookResult
from coding.extensions.runtime import ExtensionRuntime
from coding.tokens import estimate_context_tokens


@dataclass
class CodingSessionConfig:
    provider: ModelProvider
    model: str
    system: str
    storage: SessionStorage
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int = 40
    auto_compact_threshold: int | None = None
    extension_runtime: ExtensionRuntime | None = None


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
        pending_initial_entry: SessionInfoEntry | None = None,
    ):
        self.config = config
        self.harness = harness
        self.last_parent_id = last_parent_id
        self.pending_initial_entry = pending_initial_entry
        self._persistence_unsubscribe = self.harness.subscribe(self._on_agent_event)

    @classmethod
    async def load(cls, config: CodingSessionConfig) -> "CodingSession":
        entries = await config.storage.read_all()
        last_parent_id: str | None = None
        pending_initial_entry: SessionInfoEntry | None = None

        if not entries:
            info = SessionInfoEntry()
            pending_initial_entry = info

            leaf_id = None
            last_parent_id = info.id
        else:
            latest_leaf = _latest_leaf_entry(entries)

            if latest_leaf is not None:
                leaf_id = latest_leaf.entry_id
                last_parent_id = latest_leaf.entry_id
            else:
                # File Only has SessionInfoEntry, no messages yet
                leaf_id = None
                last_parent_id = entries[-1].id

        state = SessionState.from_entries(entries, leaf_id=leaf_id)

        effective_tools = list(config.tools)

        if config.extension_runtime is not None:
            effective_tools.extend(config.extension_runtime.get_all_tools())

            effective_tools = [
                config.extension_runtime.wrap_tool(t) for t in effective_tools
            ]

        harness_config = AgentHarnessConfig(
            provider=config.provider,
            model=config.model,
            system=config.system,
            tools=effective_tools,
            max_turns=config.max_turns,
        )

        harness = AgentHarness(config=harness_config, messages=state.messages)

        return cls(
            config=config,
            harness=harness,
            last_parent_id=last_parent_id,
            pending_initial_entry=pending_initial_entry,
        )

    def should_auto_compact(self) -> bool:
        if self.config.auto_compact_threshold is None:
            return False

        if len(self.harness.messages) < 2:
            return False

        tokens = estimate_context_tokens(self.harness.messages)
        return tokens > self.config.auto_compact_threshold

    async def _on_agent_event(self, event: AgentEvent):
        if isinstance(event, MessageEndEvent):
            await self._persist_message(event.message)

    async def _persist_message(self, message: AgentMessage):
        if self.pending_initial_entry is not None:
            await self.config.storage.append(self.pending_initial_entry)
            self.pending_initial_entry = None

        entry = MessageEntry(parent_id=self.last_parent_id, message=message)
        await self.config.storage.append(entry)
        self.last_parent_id = entry.id

        leaf = LeafEntry(
            parent_id=self.last_parent_id,
            entry_id=self.last_parent_id,
        )
        await self.config.storage.append(leaf)

    async def prompt(
        self,
        content: str,
        streaming_behaviour: Literal["steer", "follow_up"] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        effective_content = content

        if self.config.extension_runtime is not None:
            input_result_hook: InputHookResult = (
                await self.config.extension_runtime.run_input_hooks(effective_content)
            )

            if input_result_hook.action == "handled":
                print(f"\n[Intercepted by hook]: {input_result_hook.reply}\n")
                return

            if (
                input_result_hook.action == "continue"
                and input_result_hook.text is not None
            ):
                effective_content = input_result_hook.text

        if self.harness.is_running:
            streaming_behaviour = streaming_behaviour or "steer"

            if streaming_behaviour == "steer":
                self.harness.msg_queue_when_running.steer(effective_content)
            elif streaming_behaviour == "follow_up":
                self.harness.msg_queue_when_running.follow_up(effective_content)

            return

        if self.should_auto_compact():
            print(
                f"\n[Auto compaction triggered: context exceeded {self.config.auto_compact_threshold} tokens]\n",
                flush=True,
            )
            await self.compact()

        async for event in self.harness.prompt(effective_content):
            yield event

    async def compact(self, custom_instructions: str | None = None) -> str:
        cut = find_compaction_cut(self.harness.messages)

        if cut is None:
            return "Not enough context to compact"

        messages_to_summarize = self.harness.messages[:cut]
        retained_tail = self.harness.messages[cut:]

        summary = await generate_compaction_summary(
            provider=self.config.provider,
            model=self.config.model,
            messages_to_summarize=messages_to_summarize,
            custom_instructions=custom_instructions,
        )

        if self.pending_initial_entry is not None:
            await self.config.storage.append(self.pending_initial_entry)
            self.pending_initial_entry = None

        compaction_entry = CompactionEntry(
            parent_id=self.last_parent_id,
            summary=summary,
            retained_tail=retained_tail,
        )

        await self.config.storage.append(compaction_entry)
        self.last_parent_id = compaction_entry.id

        leaf = LeafEntry(
            parent_id=self.last_parent_id,
            entry_id=self.last_parent_id,
        )
        await self.config.storage.append(leaf)

        summary_msg = UserMessage(
            content=f"Previously conversation summary: \n{summary}"
        )
        self.harness.replace_messages([summary_msg, *retained_tail])

        return f"Compacted {len(messages_to_summarize)} messages"

    def cancel(self):
        self.harness.cancel()
