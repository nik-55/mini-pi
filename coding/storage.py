from pathlib import Path

from agent.session.entries import SessionEntry
from agent.session.jsonl import entries_from_json_lines, entry_to_json_line
from agent.session.storage import SessionStorage


class JsonlSessionStorage(SessionStorage):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _make_sure_parent_dir(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def append(self, entry: SessionEntry) -> None:
        self._make_sure_parent_dir()
        with self.path.open("a") as file:
            file.write(entry_to_json_line(entry))

    async def append_batch(self, entries: list[SessionEntry]) -> None:
        if len(entries) == 0:
            return

        self._make_sure_parent_dir()
        batch = "".join([entry_to_json_line(entry) for entry in entries])

        with self.path.open("a") as file:
            file.write(batch)

    async def read_all(self) -> list[SessionEntry]:
        if not self.path.exists():
            return []

        lines = self.path.read_text(encoding="utf-8").splitlines()

        return entries_from_json_lines(lines)
