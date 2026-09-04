from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel


class AgentTool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    execute_fn: Callable[[dict[str, Any]], Awaitable[str]]

    async def execute(self, arguments: dict[str, Any]) -> str:
        return await self.execute_fn(arguments)
