from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from coding.storage import JsonlSessionStorage


class ChatSessionFileMetadata(BaseModel):
    updated_at: datetime
    id: str
    title: str | None = None  # By default first user message


# Since we need to show metadata for all jsonl files for list sessions we do need title
# We will read mostly the first few lines to get the first user message
# Currently we only have jsonl so we do need to read it to extract any other metadata
# TODO: Study more on it
def extract_first_user_message(file_path: Path):
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
            first_user_msg = extract_first_user_message(file_path)

            title = None
            if first_user_msg:
                if len(first_user_msg) > 25:
                    title = f"{first_user_msg[:25]}..."
                else:
                    title = first_user_msg

            session_rows.append(
                ChatSessionFileMetadata(
                    updated_at=datetime.fromtimestamp(stat.st_mtime),
                    id=file_path.stem,
                    title=title,
                )
            )

        session_rows.sort(key=lambda x: x.updated_at, reverse=True)
        return session_rows

    def new_session_storage(self) -> tuple[str, JsonlSessionStorage]:
        session_id = self.generate_session_id()
        session_path = self.session_dir / f"{session_id}.jsonl"
        return session_id, JsonlSessionStorage(session_path)
