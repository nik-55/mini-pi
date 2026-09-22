from agent.tools import AgentTool
from ai.registry import Provider, register_inference_provider
from coding.commands import SlashCommand
from coding.extensions.types import HookHandler


class ExtensionAPI:
    def __init__(self, extension_name: str):
        self.extension_name = extension_name
        self.tools: list[AgentTool] = []
        self.commands: list[SlashCommand] = []
        self.hooks: dict[str, list[HookHandler]] = {}

    def register_tool(self, tool: AgentTool):
        self.tools.append(tool)

    def register_command(self, command: SlashCommand):
        self.commands.append(command)

    def register_llm_provider(self, provider: Provider) -> None:
        register_inference_provider(provider)

    # @api.on
    def on(self, event: str):
        def decorator(fn: HookHandler):
            self.hooks.setdefault(event, [])
            self.hooks[event].append(fn)
            return fn

        return decorator
