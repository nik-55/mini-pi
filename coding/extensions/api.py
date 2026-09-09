from collections.abc import Callable
from typing import Any, Awaitable, Literal

from pydantic import BaseModel

from agent.tools import AgentTool


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
    reply: str | None = None
    action: Literal["continue", "transform", "handled"] = "continue"
    # continue = leave prompt unchanged
    # transform = replace prompt text with `text`
    # handled = dont sent to agent reply to user with `reply` directly


HookHandlerOutputType = (
    ToolCallHookResult | ToolResultHookResult | InputHookResult | None
)
HookHandler = Callable[[Any], HookHandlerOutputType | Awaitable[HookHandlerOutputType]]


class ExtensionAPI:
    def __init__(self, extension_name: str):
        self.extension_name = extension_name
        self.tools: list[AgentTool] = []
        self.hooks: dict[str, list[HookHandler]] = {}

    def register_tool(self, tool: AgentTool):
        self.tools.append(tool)

    # @api.on
    def on(self, event: str):
        def decorator(fn: HookHandler):
            self.hooks.setdefault(event, [])
            self.hooks[event].append(fn)
            return fn

        return decorator
