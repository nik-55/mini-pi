from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from coding.storage import JsonlSessionStorage


class ChatSessionFileMetadata(BaseModel):
    updated_at: datetime
    id: str


class ChatSessionManager:
    def __init__(self):
        self.session_dir = Path.cwd() / ".mini-pi" / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def generate_session_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = uuid4().hex[:4]
        return f"{timestamp}_{suffix}"

    def get_session_storage(
        self, search_prefix: str
    ) -> tuple[str, JsonlSessionStorage] | None:
        target = self.session_dir / f"{search_prefix}.jsonl"

        if target.exists():
            # search_prefix == session_id
            return (search_prefix, JsonlSessionStorage(path=target))

        candidates = list(self.session_dir.glob(f"*{search_prefix}*.jsonl"))

        if len(candidates) == 1:
            matched_path = candidates[0]
            return (matched_path.stem, JsonlSessionStorage(matched_path))

        return None

    def list_sessions(self) -> list[ChatSessionFileMetadata]:
        session_rows: list[ChatSessionFileMetadata] = []

        for file_path in self.session_dir.glob("*.jsonl"):
            stat = file_path.stat()
            session_rows.append(
                ChatSessionFileMetadata(
                    updated_at=datetime.fromtimestamp(stat.st_mtime), id=file_path.stem
                )
            )

        session_rows.sort(key=lambda x: x.updated_at, reverse=True)
        return session_rows

    def new_session_storage(self) -> tuple[str, JsonlSessionStorage]:
        session_id = self.generate_session_id()
        session_path = self.session_dir / f"{session_id}.jsonl"
        return session_id, JsonlSessionStorage(session_path)
