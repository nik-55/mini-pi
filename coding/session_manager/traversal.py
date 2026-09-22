from dataclasses import dataclass

from ai.types import ThinkingLevel, UserMessage
from coding.messages import CompactionSummaryMessage, SessionMessage
from coding.session_manager.entries import (
    MessageEntry,
    ModelChangeEntry,
    SessionEntry,
    CompactionEntry,
    SessionHeader,
    SessionMetaDataEntry,
    ThinkingLevelChangeEntry,
)


class SessionTreeError(ValueError):
    pass


def entries_by_id(entries: list[SessionEntry]) -> dict[str, SessionEntry]:
    result: dict[str, SessionEntry] = {}
    for entry in entries:
        if entry.id in result:
            raise SessionTreeError(f"Duplicate entry '{entry.id}' found")
        result[entry.id] = entry

    return result


def branch_by_leaf_id(
    entries: list[SessionEntry], leaf_id: str | None
) -> list[SessionEntry]:
    if leaf_id is None:
        return []

    entries_mapping = entries_by_id(entries)

    active_branch: list[SessionEntry] = []
    seen: set[str] = set()
    current_id: str | None = leaf_id

    while current_id is not None:
        if current_id in seen:
            raise SessionTreeError(f"Cycle detected at entry {current_id}")

        entry = entries_mapping.get(current_id)
        if entry is None:
            raise SessionTreeError(f"Missing session entry: {current_id}")

        seen.add(current_id)
        active_branch.append(entry)
        current_id = entry.parent_id if not isinstance(entry, SessionHeader) else None

    active_branch.reverse()
    return active_branch


@dataclass
class SessionContext:
    messages: list[SessionMessage]
    messages_entries: list[
        SessionEntry
    ]  # Same list as messages (i.e message corresponding entry)
    model_ref: str | None = None
    thinking_level: ThinkingLevel | None = None
    session_metadata: SessionMetaDataEntry | None = None


def entry_to_message(entry: SessionEntry) -> SessionMessage | None:
    if isinstance(entry, MessageEntry):
        return entry.message

    if isinstance(entry, CompactionEntry):
        return CompactionSummaryMessage(summary=entry.summary)

    return


def build_session_context(
    entries: list[SessionEntry],
    leaf_id: str | None = None,
) -> SessionContext:
    branch = branch_by_leaf_id(entries, leaf_id)

    messages_entries: list[SessionEntry] = []
    latest_compaction_index: int | None = None

    # Traverse branch backwards
    for i in range(len(branch) - 1, -1, -1):
        if isinstance(branch[i], CompactionEntry):
            latest_compaction_index = i
            break

    if latest_compaction_index is not None:
        compaction_entry: CompactionEntry = branch[latest_compaction_index]
        messages_entries.append(compaction_entry)

        # Message from first_kept_entry_id to compaction entry
        found_first_kept_entry = False
        for i in range(latest_compaction_index):
            entry = branch[i]

            if entry.id == compaction_entry.first_kept_entry_id:
                found_first_kept_entry = True

            if found_first_kept_entry and isinstance(entry, MessageEntry):
                messages_entries.append(entry)

        tail_entries = branch[latest_compaction_index + 1 :]
    else:
        tail_entries = branch

    for entry in tail_entries:
        if isinstance(entry, MessageEntry):
            messages_entries.append(entry)

    messages: list[SessionMessage] = []
    for entry in messages_entries:
        message = entry_to_message(entry)

        # message should not be None as message_entries formed with entry that do carry message
        if message is None:
            raise ValueError(f"{entry} has no corresponding message")

        messages.append(message)

    session_metadata: SessionMetaDataEntry | None = None
    model_ref: str | None = None
    thinking_level: ThinkingLevel | None = None

    for entry in branch:
        if isinstance(entry, SessionMetaDataEntry):
            session_metadata = entry
        elif isinstance(entry, ModelChangeEntry):
            model_ref = entry.model_ref
        elif isinstance(entry, ThinkingLevelChangeEntry):
            thinking_level = entry.thinking_level

    return SessionContext(
        session_metadata=session_metadata,
        model_ref=model_ref,
        thinking_level=thinking_level,
        messages=messages,
        messages_entries=messages_entries,
    )


def get_rewind_entries(
    entries: list[SessionEntry],
    leaf_id: str,
) -> list[MessageEntry]:
    branch = branch_by_leaf_id(entries, leaf_id)

    latest_compaction_index = None

    for i in range(len(branch) - 1, -1, -1):
        if isinstance(branch[i], CompactionEntry):
            latest_compaction_index = i
            break

    # TODO: handling of retained tail messages (i.e branch[first_kept_entry_index:latest_compaction_index])
    # for rewind need study

    post_compaction_entries = (
        branch[latest_compaction_index + 1 :]
        if latest_compaction_index is not None
        else branch
    )

    targets: list[MessageEntry] = []

    for entry in post_compaction_entries:
        if isinstance(entry, MessageEntry) and isinstance(entry.message, UserMessage):
            targets.append(entry)

    return targets
