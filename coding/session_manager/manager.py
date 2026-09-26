from datetime import datetime
import json
from pathlib import Path
import re
from typing import Union
from uuid import uuid4

from pydantic import BaseModel

from ai.types import Message, MessageType
from coding.session_manager.entries import (
    CompactionEntry,
    MessageEntry,
    SessionEntry,
    SessionHeader,
    entry_from_json_line,
    entry_to_json_line,
)
from coding.session_manager.traversal import (
    SessionContext,
    branch_by_leaf_id,
    entries_by_id,
    get_rewind_entries,
    build_session_context,
)


class ChatSessionFileMetadata(BaseModel):
    updated_at: datetime
    id: str
    title: str | None = None  # By default first user message


# TODO: Base session dir need more standarization
def get_base_session_dir() -> Path:
    return Path.home() / ".mini-pi" / "sessions"


# TODO: We are using everywhere Path.cwd() loosely which can cause issues as we want to
# define cwd at startup or when user change it
def get_default_session_dir(cwd: Path | None = None) -> Path:
    resolved_cwd = Path(cwd or Path.cwd()).resolve()
    safe_path = (
        re.sub(r"[/:]+", "-", resolved_cwd.as_posix()).strip("-").strip() or "root"
    )
    safe_path = f"--{safe_path}--"
    return get_base_session_dir() / safe_path


# Since we need to show metadata for all jsonl files for list sessions we do need title
# We will read mostly the first few lines to get the first user message
# Currently we only have jsonl so we do need to read it to extract any other metadata
# TODO: Study more on it
def extract_first_user_message(file_path: Path) -> str | None:
    try:
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if (
                    record.get("type") == "message"
                    and record.get("message", {}).get("role") == "user"
                ):
                    content = record["message"].get("content", None) or ""

                    if content:
                        return (" ".join(content.split())).strip()
    except Exception:
        pass

    return


def list_sessions(session_dir: Path | None = None) -> list[ChatSessionFileMetadata]:
    session_dir = session_dir or get_default_session_dir()

    session_rows: list[ChatSessionFileMetadata] = []

    for file_path in session_dir.glob("*.jsonl"):
        stat = file_path.stat()
        first_user_msg = extract_first_user_message(file_path)

        title = None
        if first_user_msg:
            title = (
                f"{first_user_msg[:25]}..."
                if len(first_user_msg) > 25
                else first_user_msg
            )

        session_rows.append(
            ChatSessionFileMetadata(
                updated_at=datetime.fromtimestamp(stat.st_mtime),
                id=file_path.stem,
                title=title,
            )
        )

    session_rows.sort(key=lambda x: x.updated_at, reverse=True)
    return session_rows


class ChatSessionManager:
    def __init__(
        self,
        session_id: str,
        session_file_path: Path,
        cwd: Path,
        entries: list[SessionEntry] | None = None,
        is_session_file_exist: bool = False,
    ):
        self.session_id = session_id
        self.session_file_path = session_file_path
        self.cwd = cwd
        self.entries: list[SessionEntry] = entries or []
        self.entries_mapping: dict[str, SessionEntry] = entries_by_id(self.entries)
        self.is_session_file_exist = is_session_file_exist

        self.leaf_id = (
            self.entries[-1].id if len(self.entries) > 1 else None
        )  # SessionHeader is first entry

    @classmethod
    def generate_session_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = uuid4().hex[:4]
        return f"{timestamp}_{suffix}"

    @classmethod
    def new_session(
        cls, cwd: Path | None = None, session_id: str | None = None
    ) -> "ChatSessionManager":
        session_id = session_id or cls.generate_session_id()
        resolved_cwd = (cwd or Path.cwd()).resolve()
        session_file_path = (
            get_default_session_dir(resolved_cwd) / f"{session_id}.jsonl"
        )

        header = SessionHeader(cwd=str(resolved_cwd), id=session_id)
        return cls(
            session_id=session_id,
            session_file_path=session_file_path,
            cwd=resolved_cwd,
            entries=[header],
            is_session_file_exist=False,
        )

    @classmethod
    def read_session_file(cls, file_path: Path) -> "ChatSessionManager":
        if not file_path.exists():
            raise FileNotFoundError(f"Session file not found: {file_path}")

        lines = file_path.read_text(encoding="utf-8").splitlines()
        entries: list[SessionEntry] = []

        for l in lines:
            entry = entry_from_json_line(l)
            if entry is not None:
                entries.append(entry)

        if not entries or not isinstance(entries[0], SessionHeader):
            raise ValueError(f"Invalid session file at {file_path}")

        session_id = entries[0].id
        cwd = Path(entries[0].cwd)

        return cls(
            session_id=session_id,
            session_file_path=file_path,
            cwd=cwd,
            entries=entries,
            is_session_file_exist=True,
        )

    @classmethod
    def search_session(
        cls,
        search_prefix: str,
        cwd: Path,
    ) -> Union["ChatSessionManager", None]:  # using | operator in this senario give error in python 3.12
        session_dir = get_default_session_dir(cwd)
        target_file_path = session_dir / f"{search_prefix}.jsonl"

        if target_file_path.exists():
            # search_prefix == session_id
            return cls.read_session_file(target_file_path)

        candidates = list(session_dir.glob(f"*{search_prefix}*.jsonl"))

        if len(candidates) == 1:
            return cls.read_session_file(candidates[0])

        return None

    # Create jsonl file only after first assistant message
    # This ensure stale session file (i.e only session header or user message with no assistant message) are not
    # persisted
    def _persist(self, entry: SessionEntry) -> None:
        has_assistant = any(
            isinstance(e, MessageEntry)
            and e.message.role == MessageType.ASSISTANT
            and e.message.stop_reason not in ("error", "aborted")
            for e in self.entries
        )

        if not has_assistant:
            return

        self.session_file_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.is_session_file_exist:
            with self.session_file_path.open("w", encoding="utf-8") as f:
                for e in self.entries:
                    f.write(entry_to_json_line(e))

            self.is_session_file_exist = True
        else:
            with self.session_file_path.open("a", encoding="utf-8") as f:
                f.write(entry_to_json_line(entry))

    def _append_entry(self, entry: SessionEntry) -> None:
        self.entries.append(entry)
        self.entries_mapping[entry.id] = entry

        if not isinstance(entry, SessionHeader):
            self.leaf_id = entry.id

        self._persist(entry)

    def append_message(self, message: Message) -> str:
        entry = MessageEntry(parent_id=self.leaf_id, message=message)
        self._append_entry(entry)
        return entry.id

    def append_compaction(self, summary: str, first_kept_entry_id: str) -> str:
        entry = CompactionEntry(
            parent_id=self.leaf_id,
            summary=summary,
            first_kept_entry_id=first_kept_entry_id,
        )

        self._append_entry(entry)
        return entry.id

    # def append_thinking_level_change(self, thinking_level: ThinkingLevel) -> str:
    #     entry = ThinkingLevelChangeEntry(
    #         parent_id=self.leaf_id,
    #         thinking_level=thinking_level,
    #     )

    #     self._append_entry(entry)
    #     return entry.id

    # def append_model_change(self, model_ref: str) -> str:
    #     entry = ModelChangeEntry(
    #         parent_id=self.leaf_id,
    #         model_ref=model_ref,
    #     )

    #     self._append_entry(entry)
    #     return entry.id

    def reset_leaf(self):
        self.leaf_id = None

    def branch(self, entry_id: str) -> None:
        if entry_id not in self.entries_mapping:
            raise ValueError(f"Entry {entry_id} not found")

        self.leaf_id = entry_id

    def build_session_context(self) -> SessionContext:
        return build_session_context(self.entries, leaf_id=self.leaf_id)

    @property
    def rewind_entries(self) -> list[MessageEntry]:
        return get_rewind_entries(self.entries, self.leaf_id)

    def get_active_branch(self) -> list[SessionEntry]:
        return branch_by_leaf_id(self.entries, self.leaf_id)
