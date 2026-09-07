from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from agent.cancellation import CancellationSignal


class AgentTool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    execute_fn: Callable[[dict[str, Any], CancellationSignal | None], Awaitable[str]]

    async def execute(
        self,
        arguments: dict[str, Any],
        signal: CancellationSignal | None = None,
    ) -> str:
        try:
            return await self.execute_fn(arguments, signal)
        except TypeError:
            return await self.execute_fn(arguments)
