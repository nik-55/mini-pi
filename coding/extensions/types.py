from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel


class ToolCallHookPayload(BaseModel):
    tool_name: str
    arguments: dict[str, Any]


class ToolCallHookResult(BaseModel):
    block: bool = False
    arguments: dict[str, Any] | None = None
    reason: str | None = None


class ToolResultHookPayload(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result: str


class ToolResultHookResult(BaseModel):
    result: str | None = None


class InputHookPayload(BaseModel):
    text: str


class InputHookResult(BaseModel):
    text: str | None = None
    action: Literal["continue", "transform", "handled"] = "continue"
    # continue = leave prompt unchanged
    # transform = replace prompt text with `text`
    # handled = dont sent to agent (assume: user is notified by hook handler)


class ExtensionUIContext(ABC):
    @abstractmethod
    async def select(self, title: str, options: list[str]) -> str | None: ...

    async def confirm(self, title: str, message: str) -> bool:
        choice = await self.select(f"\n{title}\n{message}", options=["Yes", "No"])
        return choice == "Yes"

    @abstractmethod
    def notify(self, message: str, level: str = "info") -> None: ...


# Overall environment context passed into handler. It bundles things that an extension might need
@dataclass
class ExtensionContext:
    cwd: str
    ui: ExtensionUIContext | None = None


HookHandlerOutputType = (
    ToolCallHookResult | ToolResultHookResult | InputHookResult | None
)
HookHandler = Callable[
    [Any, ExtensionContext], HookHandlerOutputType | Awaitable[HookHandlerOutputType]
]


@dataclass
class ExtensionCommand:
    name: str
    description: str
    handler: Callable[[str, ExtensionContext], Awaitable[None] | None]
