import inspect
from typing import Any

from agent.tools import AgentTool
from coding.commands import SlashCommand
from coding.extensions.api import (
    ExtensionAPI,
    HookHandler,
    InputHookPayload,
    InputHookResult,
    ToolCallHookPayload,
    ToolCallHookResult,
    ToolResultHookPayload,
    ToolResultHookResult,
)


class ExtensionRuntime:
    def __init__(self):
        self.extensions: list[ExtensionAPI] = []

    def register_extension(self, api: ExtensionAPI):
        self.extensions.append(api)

    def _handlers_by_event(self, event: str) -> list[HookHandler]:
        handlers: list[HookHandler] = []

        for ext in self.extensions:
            handlers.extend(ext.hooks.get(event, []))

        return handlers

    def get_all_tools(self) -> list[AgentTool]:
        tools: list[AgentTool] = []

        for ext in self.extensions:
            tools.extend(ext.tools)

        return tools

    def get_all_commands(self) -> list[SlashCommand]:
        commands: list[SlashCommand] = []

        for ext in self.extensions:
            commands.extend(ext.commands)

        return commands

    def wrap_tool(self, tool: AgentTool) -> AgentTool:
        original_execute = tool.execute

        async def wrapped_execute(arguments: dict[str, Any], signal: Any = None):
            effective_args = arguments

            for handler in self._handlers_by_event("tool_call"):
                payload = ToolCallHookPayload(
                    tool_name=tool.name,
                    arguments=effective_args,
                )
                res = handler(payload)

                if inspect.isawaitable(res):
                    res = await res

                if isinstance(res, ToolCallHookResult):
                    if res.block:
                        reason = res.reason or "Blocked by extension"
                        return f"Tool call blocked by extension: {reason}"

                    if res.arguments is not None:
                        effective_args = res.arguments

            result = await original_execute(effective_args, signal)

            effective_result = str(result)

            for handler in self._handlers_by_event("tool_result"):
                payload = ToolResultHookPayload(
                    tool_name=tool.name,
                    arguments=effective_args,
                    result=effective_result,
                )

                res = handler(payload)
                if inspect.isawaitable(res):
                    res = await res

                if isinstance(res, ToolResultHookResult) and res.result is not None:
                    effective_result = res.result

            return effective_result

        return AgentTool(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            execute_fn=wrapped_execute,
        )

    async def run_input_hooks(self, text: str) -> InputHookResult:
        current_text = text

        for handler in self._handlers_by_event("input"):
            payload = InputHookPayload(text=current_text)
            res = handler(payload)

            if inspect.isawaitable(res):
                res = await res

            if isinstance(res, InputHookResult):
                if res.action == "handled":
                    return res
                if res.action == "transform" and res.text is not None:
                    current_text = res.text

        return InputHookResult(action="continue", text=current_text)
