from collections.abc import Callable
from dataclasses import replace

from coding.session import CodingSession, CodingSessionConfig
from coding.session_manager.manager import ChatSessionManager


class CodingSessionRuntime:
    def __init__(self, session: CodingSession):
        self.session = session
        self._rebind_session: Callable[[CodingSession], None] | None = None

    def set_rebind_session(
        self, rebind_session: Callable[[CodingSession], None]
    ) -> None:
        self._rebind_session = rebind_session

    async def _replace(self, chat_session_manager: ChatSessionManager) -> None:
        self.session.cancel()

        config = replace(self.session.config, chat_session_manager=chat_session_manager)
        self.session = await CodingSession.load(config)

        if self._rebind_session is not None:
            self._rebind_session(self.session)

    async def new_session(self) -> None:
        await self._replace(
            ChatSessionManager.new_session(
                cwd=self.session.chat_session_manager.cwd,
            )
        )

    async def switch_session(self, session_id: str) -> None:
        chat_session_manager = ChatSessionManager.search_session(
            session_id,
            cwd=self.session.chat_session_manager.cwd,
        )

        if chat_session_manager is None:
            raise ValueError(f"No session matching '{session_id}'")

        await self._replace(chat_session_manager)

    @classmethod
    async def create(cls, config: CodingSessionConfig) -> "CodingSessionRuntime":
        return cls(await CodingSession.load(config))
