from typing import Any

from pydantic import BaseModel


class AgentTool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

    async def execute(self, arguments: dict[str, Any]) -> str:
        raise NotImplementedError
