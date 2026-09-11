from typing import Any

from agent.tools import AgentTool
from coding.commands import CommandContext, CommandResult, SlashCommand
from coding.extensions.api import (
    ExtensionAPI,
    InputHookPayload,
    InputHookResult,
    ToolCallHookPayload,
    ToolCallHookResult,
    ToolResultHookPayload,
    ToolResultHookResult,
)


def setup(api: ExtensionAPI):
    def ping_handler(context: CommandContext) -> CommandResult:
        arg_text = f" with args '{context.args}'" if context.args else ""
        return CommandResult(
            message=f"PONG from extensions{arg_text}!",
        )

    api.register_command(
        SlashCommand(
            name="ping",
            description="Pong",
            handler=ping_handler,
            aliases=("shout",),
        )
    )

    async def get_current_temperature(arguments: dict[str, Any], signal=None) -> str:
        city = arguments.get("city", None)
        if city is None:
            return f"Error: Please mention city name"
        return f"Current Temperature in {city} is 28 deg celcius"

    api.register_tool(
        AgentTool(
            name="get_current_temperature",
            description="Get the current temperature of city",
            parameters={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Name of city",
                    },
                },
                "required": ["city"],
            },
            execute_fn=get_current_temperature,
        )
    )

    @api.on("input")
    def on_input(payload: InputHookPayload):
        if payload.text.strip() == "@ping":
            return InputHookResult(
                action="transform",
                text="Reply with exact word: MiniPI_PONG",
            )

        if payload.text.strip() == "@about":
            return InputHookResult(
                action="handled",
                reply="Minipi extension runtime v1.0. All systems operational",
            )

    @api.on("tool_call")
    def on_tool_call(payload: ToolCallHookPayload):
        if payload.tool_name == "bash":
            cmd = payload.arguments.get("command", None) or ""

            if cmd.strip() == "whoami":
                return ToolCallHookResult(
                    block=True,
                    reason="Security policy: 'whoami' is blocked in the environment",
                )

    @api.on("tool_result")
    def on_tool_result(payload: ToolResultHookPayload):
        if payload.tool_name == "get_current_temperature":
            decorated = payload.result + "\n[SECURITY AUDIT: secured and verified]"
            return ToolResultHookResult(result=decorated)
