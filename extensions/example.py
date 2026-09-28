from typing import Any

from agent.tools import AgentTool
from coding.extensions.api import ExtensionAPI
from coding.extensions.types import (
    ExtensionContext,
    InputHookPayload,
    InputHookResult,
    ToolCallHookPayload,
    ToolCallHookResult,
    ToolResultHookPayload,
    ToolResultHookResult,
)


def setup(api: ExtensionAPI):
    def ping_handler(args: str, context: ExtensionContext) -> None:
        if context.ui is None:
            return

        arg_text = f" with args '{args}'" if args else ""
        context.ui.notify(
            message=f"PONG from extensions{arg_text}!",
        )
        return

    api.register_command(
        name="ping",
        description="Pong",
        handler=ping_handler,
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
    async def on_input(payload: InputHookPayload, context: ExtensionContext):
        if payload.text.strip() == "@ping":
            return InputHookResult(
                action="transform",
                text="Reply with exact word: MiniPI_PONG",
            )

        if payload.text.strip() == "@about":
            if context.ui is not None:
                context.ui.notify(
                    message="Minipi extension runtime v1.0. All systems operational",
                    level="info",
                )

            return InputHookResult(action="handled")

        if payload.text.strip() == "@enroll":
            confirm = False
            if context.ui is not None:
                confirm = await context.ui.confirm(
                    "Do you want to proceed?",
                    "If you continue, you accepted terms of minipi.",
                )

            if not confirm:
                if context.ui is not None:
                    context.ui.notify(
                        message="Aborting enrollment",
                        level="info",
                    )
                return InputHookResult(action="handled")

            return InputHookResult(
                action="transform",
                text=(
                    "User is enrolled to our flagship minipi subscription."
                    "Do greet them and tell use /help to get started."
                ),
            )

    @api.on("tool_call")
    def on_tool_call(payload: ToolCallHookPayload, context: ExtensionContext):
        if payload.tool_name == "bash":
            cmd = payload.arguments.get("command", None) or ""

            if cmd.strip() == "whoami":
                return ToolCallHookResult(
                    block=True,
                    reason="Security policy: 'whoami' is blocked in the environment",
                )

    @api.on("tool_result")
    def on_tool_result(payload: ToolResultHookPayload, context: ExtensionContext):
        if payload.tool_name == "get_current_temperature":
            decorated = payload.result + "\n[SECURITY AUDIT: secured and verified]"
            return ToolResultHookResult(result=decorated)
