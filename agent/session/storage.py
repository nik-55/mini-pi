import abc

from agent.session.entries import SessionEntry


class SessionStorage(abc.ABC):
    async def append(self, entry: SessionEntry) -> None:
        pass

    async def append_batch(self, entries: list[SessionEntry]) -> None:
        pass

    async def read_all(self) -> list[SessionEntry]:
        pass
