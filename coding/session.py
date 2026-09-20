from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from agent.events import AgentEvent, MessageEndEvent
from agent.harness import AgentHarness, AgentHarnessConfig
from agent.provider import ModelProvider
from agent.tools import AgentTool
from ai.types import AIModel, AgentMessage, UserMessage
from coding.compaction import find_compaction_cut, generate_compaction_summary
from coding.extensions.runtime import ExtensionRuntime
from coding.extensions.types import InputHookResult
from coding.tokens import estimate_context_tokens
from coding.session_manager.entries import MessageEntry
from coding.session_manager.manager import ChatSessionManager
from coding.session_manager.traversal import entries_by_id


@dataclass
class CodingSessionConfig:
    provider: ModelProvider
    model: AIModel
    system: str
    chat_session_manager: ChatSessionManager
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int = 40
    auto_compact_threshold: int | None = None
    extension_runtime: ExtensionRuntime | None = None


class RewindTarget(BaseModel):
    entry_id: str
    text: str


class CodingSession:
    def __init__(
        self,
        config: CodingSessionConfig,
        harness: AgentHarness,
        chat_session_manager: ChatSessionManager,
    ):
        self.config = config
        self.harness = harness
        self.chat_session_manager = chat_session_manager
        self._persistence_unsubscribe = self.harness.subscribe(self._on_agent_event)

    @classmethod
    async def load(cls, config: CodingSessionConfig) -> "CodingSession":
        chat_session_manager = config.chat_session_manager
        context = chat_session_manager.build_session_context()

        effective_tools = config.tools
        tool_map = {t.name: t for t in effective_tools}

        if config.extension_runtime is not None:
            extension_tools = config.extension_runtime.get_all_tools()

            for ext_tool in extension_tools:
                # Extension can override inbuilt tools
                tool_map[ext_tool.name] = ext_tool

            effective_tools = [
                config.extension_runtime.wrap_tool(t) for t in tool_map.values()
            ]

        harness_config = AgentHarnessConfig(
            provider=config.provider,
            model=config.model,
            system=config.system,
            tools=effective_tools,
            max_turns=config.max_turns,
        )

        harness = AgentHarness(config=harness_config, messages=context.messages)

        return cls(
            config=config,
            harness=harness,
            chat_session_manager=chat_session_manager,
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
            self.chat_session_manager.append_message(event.message)

    async def get_rewind_targets(self) -> list[RewindTarget]:
        if self.chat_session_manager.leaf_id is None:
            return []

        rewind_entries = self.chat_session_manager.rewind_entries

        return [
            RewindTarget(
                entry_id=e.id,
                text=e.message.content,
            )
            for e in reversed(rewind_entries)
        ]

    async def rewind_to(self, entry_id: str) -> list[AgentMessage]:
        if self.harness.is_running:
            raise RuntimeError("Cannot rewind while agent is running")

        if self.chat_session_manager.leaf_id is None:
            return []

        rewind_entries = self.chat_session_manager.rewind_entries

        target_entry = entries_by_id(rewind_entries).get(entry_id, None)

        if target_entry is None:
            raise ValueError(f"Unknown session entry: {entry_id}")

        new_leaf_id = target_entry.parent_id
        self.chat_session_manager.branch(new_leaf_id)

        context = self.chat_session_manager.build_session_context()
        self.harness.replace_messages(context.messages)

        return context.messages

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
                return

            if (
                input_result_hook.action == "transform"
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

        active_branch = self.chat_session_manager.get_active_branch()
        message_entries = [e for e in active_branch if isinstance(e, MessageEntry)]

        if cut >= len(message_entries):
            raise ValueError(f"Invalid compaction cut")

        first_kept_entry_id = message_entries[cut].id
        self.chat_session_manager.append_compaction(
            summary=summary,
            first_kept_entry_id=first_kept_entry_id,
        )

        summary_msg = UserMessage(
            content=f"Previously conversation summary: \n{summary}"
        )
        self.harness.replace_messages([summary_msg, *retained_tail])

        return f"Compacted {len(messages_to_summarize)} messages"

    def cancel(self):
        self.harness.cancel()
