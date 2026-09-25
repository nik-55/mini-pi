from collections.abc import Callable
from dataclasses import dataclass, field
import inspect
from typing import Any

from pydantic import BaseModel

from ai.cancellation import CancellationSignal
from agent.events import AgentEvent, MessageEndEvent
from agent.harness import AgentHarness, AgentHarnessConfig
from agent.tools import AgentTool
from ai.registry import stream
from ai.types import AIModel, AssistantMessage
from coding.compaction.compaction import (
    format_file_operations,
    generate_compaction_summary,
)
from coding.compaction.types import CompactionSettings
from coding.compaction.prepare import check_compaction_threshold, prepare_compaction
from coding.compaction.tokens import (
    estimate_context_tokens,
    estimate_message_tokens,
    extract_usage_tokens,
)
from coding.extensions.runtime import ExtensionRuntime
from coding.extensions.types import InputHookResult
from coding.events import (
    CompactionReason,
    CompactionStartEvent,
    CompactionEndEvent,
    SessionEvent,
)
from coding.messages import SessionMessage, convert_message_to_llm_compatible
from coding.session_manager.entries import CompactionEntry, MessageEntry
from coding.session_manager.manager import ChatSessionManager
from coding.session_manager.traversal import entries_by_id


@dataclass
class CodingSessionConfig:
    model: AIModel
    system: str
    chat_session_manager: ChatSessionManager
    compaction_settings: CompactionSettings
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int = 40
    extension_runtime: ExtensionRuntime | None = None


class RewindTarget(BaseModel):
    entry_id: str
    text: str


class CodingSession:
    def __init__(
        self,
        config: CodingSessionConfig,
        harness: AgentHarness[SessionMessage],
        chat_session_manager: ChatSessionManager,
    ):
        self.config = config
        self.harness = harness
        self.chat_session_manager = chat_session_manager
        self.harness.subscribe(
            self._on_agent_event
        )  # It returns unsubscribe function currently not used
        self._listerners: list[Callable[[SessionEvent], Any]] = []
        self._compaction_signal: CancellationSignal | None = None

    @property
    def is_compacting(self) -> bool:
        return self._compaction_signal is not None

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

        harness_config = AgentHarnessConfig[SessionMessage](
            stream_fn=stream,
            model=config.model,
            system=config.system,
            tools=effective_tools,
            max_turns=config.max_turns,
            convert_message_to_llm_compatible=convert_message_to_llm_compatible,
        )

        harness = AgentHarness[SessionMessage](
            config=harness_config, messages=context.messages
        )

        return cls(
            config=config,
            harness=harness,
            chat_session_manager=chat_session_manager,
        )

    def set_model(self, model: AIModel) -> None:
        # TODO
        self.config.model = model
        self.harness.config.model = model

    def subscribe(self, listener: Callable[[SessionEvent], Any]) -> Callable[[], None]:
        self._listerners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listerners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    async def _notify(self, event: SessionEvent) -> None:
        snapshot_listeners = list(self._listerners)

        for listerner in snapshot_listeners:
            result = listerner(event)

            if inspect.isawaitable(result):
                await result

    def _is_usage_stale(self) -> bool:
        # Whether usage is stale
        # When compaction happens with tail messages, then those tail assitant message report usage
        # that is stale after compaction.
        # Check whether any new assistant message land after compaction otherwise mark the usage stale

        # walk backward
        # If CompactionEntry found first -> usage is stale
        # If assistant message and valid usage can be extracted -> usage is valid
        # TODO: why we call get_active_branch at different places

        for entry in reversed(self.chat_session_manager.get_active_branch()):
            if isinstance(entry, CompactionEntry):
                return True

            if (
                isinstance(entry, MessageEntry)
                and isinstance(entry.message, AssistantMessage)
                and extract_usage_tokens(entry.message) is not None
            ):
                return False

        return False

    def _last_assistant_message(self) -> AssistantMessage | None:
        for m in reversed(self.harness.messages):
            if isinstance(m, AssistantMessage):
                return m
        return

    def should_auto_compact(self) -> bool:
        settings = self.config.compaction_settings

        if not settings.enabled:
            return False

        if self._is_usage_stale():
            tokens = sum(estimate_message_tokens(m) for m in self.harness.messages)
        else:
            tokens = estimate_context_tokens(self.harness.messages)

        return check_compaction_threshold(
            context_tokens=tokens,
            context_window=self.config.model.context_window,
            settings=self.config.compaction_settings,
        )

    async def _on_agent_event(self, event: AgentEvent):
        if isinstance(event, MessageEndEvent):
            self.chat_session_manager.append_message(event.message)

        await self._notify(event)

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

    async def rewind_to(self, entry_id: str) -> list[SessionMessage]:
        if self.harness.is_running or self.is_compacting:
            raise RuntimeError("Cannot rewind while another request is running")

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

    async def steer(self, content: str) -> None:
        effective_content = await self._run_input_hooks(content)

        if effective_content is None:
            return

        self.harness.msg_queue_when_running.steer(effective_content)

    async def follow_up(self, content: str) -> None:
        effective_content = await self._run_input_hooks(content)

        if effective_content is None:
            return

        self.harness.msg_queue_when_running.follow_up(effective_content)

    async def _run_input_hooks(self, content: str) -> str | None:
        if self.config.extension_runtime is not None:
            input_result_hook: InputHookResult = (
                await self.config.extension_runtime.run_input_hooks(content)
            )

            if input_result_hook.action == "handled":
                return

            if (
                input_result_hook.action == "transform"
                and input_result_hook.text is not None
            ):
                return input_result_hook.text

        return content

    async def prompt(
        self,
        content: str,
    ) -> None:
        if self.is_compacting:
            # TODO: we need to inform subscriber that compacting is in progress
            return

        if self.harness.is_running:
            # TODO: inform agent is already running
            return

        effective_content = await self._run_input_hooks(content)

        if effective_content is None:
            return

        # Before sending prompt to llm
        if self.should_auto_compact():
            await self.compact(reason="threshold")

        await self.harness.prompt(effective_content)

        # After the run
        last = self._last_assistant_message()

        if last and last.stop_reason != "aborted" and self.should_auto_compact():
            await self.compact(reason="threshold")

    async def compact(
        self,
        reason: CompactionReason,
        custom_instructions: str | None = None,
    ) -> None:
        if self.harness.is_running or self.is_compacting:
            # TODO
            return

        await self._notify(CompactionStartEvent(reason=reason))

        signal = CancellationSignal()
        self._compaction_signal = signal

        try:
            context = self.chat_session_manager.build_session_context()
            preparation = prepare_compaction(
                context.messages_entries,
                self.config.compaction_settings,
            )

            if preparation is None:
                # TODO
                await self._notify(
                    CompactionEndEvent(error_message="Unable to find valid cut point")
                )
                return

            summary = await generate_compaction_summary(
                stream_fn=self.harness.config.stream_fn,
                model=self.config.model,
                messages_to_summarize=preparation.messages_to_summarize,
                previous_summary=preparation.previous_summary,
                custom_instructions=custom_instructions,
                signal=signal,
            )

            if signal.is_cancelled():
                await self._notify(
                    CompactionEndEvent(error_message="Compaction Cancelled")
                )
                return

            file_operations_str = format_file_operations(
                preparation.messages_to_summarize
            )

            if file_operations_str:
                summary += "\n\n" + file_operations_str

            self.chat_session_manager.append_compaction(
                summary=summary,
                first_kept_entry_id=preparation.first_kept_entry_id,
            )

            context = self.chat_session_manager.build_session_context()
            self.harness.replace_messages(context.messages)

            await self._notify(
                CompactionEndEvent(
                    result=f"Compacted {len(preparation.messages_to_summarize)} messages"
                )
            )
        except Exception as err:
            await self._notify(CompactionEndEvent(error_message=str(err)))
        finally:
            self._compaction_signal = None

    def cancel(self):
        self.harness.cancel()

        if self._compaction_signal is not None:
            self._compaction_signal.cancel()
