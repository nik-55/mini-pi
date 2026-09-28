from collections.abc import Awaitable
from typing import Callable

from agent.tools import AgentTool
from ai.registry import Provider, register_inference_provider
from coding.extensions.types import ExtensionCommand, ExtensionContext, HookHandler


class ExtensionAPI:
    def __init__(self, extension_name: str):
        self.extension_name = extension_name
        self.tools: list[AgentTool] = []
        self.commands: list[ExtensionCommand] = []
        self.hooks: dict[str, list[HookHandler]] = {}

    def register_tool(self, tool: AgentTool):
        self.tools.append(tool)

    def register_command(
        self,
        name: str,
        description: str,
        handler: Callable[[str, ExtensionContext], Awaitable[None] | None],
    ):
        self.commands.append(
            ExtensionCommand(
                name,
                description,
                handler,
            )
        )

    def register_llm_provider(self, provider: Provider) -> None:
        register_inference_provider(provider)

    # @api.on
    def on(self, event: str):
        def decorator(fn: HookHandler):
            self.hooks.setdefault(event, [])
            self.hooks[event].append(fn)
            return fn

        return decorator
