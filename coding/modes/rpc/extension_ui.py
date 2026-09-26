import asyncio
import uuid

from coding.extensions.types import ExtensionUIContext
from coding.modes.rpc.output import emit
from coding.modes.rpc.types import (
    ExtensionUIRequest,
    ExtensionUIResponse,
    NotifyUIRequestPayload,
    SelectUIRequestPayload,
)


class RpcExtensionUI(ExtensionUIContext):
    def __init__(
        self,
        pending_ui_tasks: dict[str, asyncio.Future[ExtensionUIResponse]],
    ):
        self.pending_ui_tasks = pending_ui_tasks

    async def select(self, title: str, options: list[str]) -> str | None:
        req = ExtensionUIRequest(
            id=uuid.uuid4().hex[:6],
            payload=SelectUIRequestPayload(title=title, options=options),
        )

        future: asyncio.Future[ExtensionUIResponse] = (
            asyncio.get_event_loop().create_future()
        )

        self.pending_ui_tasks[req.id] = future

        emit(req.model_dump(mode="json"))

        try:
            resp = await future
        finally:
            self.pending_ui_tasks.pop(req.id, None)

        if resp.cancelled:
            return

        return resp.value

    def notify(self, message: str, level: str = "info") -> None:
        req = ExtensionUIRequest(
            id=uuid.uuid4().hex[:6],
            payload=NotifyUIRequestPayload(message=message, notify_type=level),
        )

        emit(req.model_dump(mode="json"))
