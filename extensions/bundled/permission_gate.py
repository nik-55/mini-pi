import os
from typing import Literal

from coding.commands import CommandContext, CommandResult, SlashCommand
from coding.extensions.api import ExtensionAPI

# TODO: Not sure if we should import internal functions in extension
from coding.tools.bash import is_sandbox_available

from coding.extensions.types import (
    ExtensionContext,
    ToolCallHookPayload,
    ToolCallHookResult,
)

# TODO: use extension context for setting mode rather than global variable
# default to auto when sandbox otherwise auto
# TODO: Sandbox should be global setting the current way to check using bwrap may cause unexpected behaviour
permission_mode: Literal["auto", "ask"]


def setup(api: ExtensionAPI):
    global permission_mode

    if not is_sandbox_available():
        permission_mode = "ask"
    else:
        permission_mode = "auto"

    @api.on("tool_call")
    async def on_tool_call(
        payload: ToolCallHookPayload,
        context: ExtensionContext,
    ) -> ToolCallHookResult | None:
        global permission_mode

        if payload.tool_name != "bash":
            return

        if permission_mode == "ask":
            if context.ui is None:
                return ToolCallHookResult(
                    block=True,
                    reason="Bash command blocked: No sandbox. No channel exist for user confirmation",
                )

            command = payload.arguments.get("command", "")
            confirm = await context.ui.confirm(
                title="Execute bash command", message=f"{command}"
            )

            if not confirm:
                return ToolCallHookResult(
                    block=True,
                    reason="Bash command rejected by user",
                )

            return

    def permission_mode_command_handler(context: CommandContext) -> CommandResult:
        global permission_mode

        arg = context.args.strip().lower() if context.args else None

        if not arg:
            sandbox_status = "available" if is_sandbox_available() else "unavailable"
            return CommandResult(
                message=f"Current bash permission mode '{permission_mode}' (sandbox: {sandbox_status})"
            )

        if arg == "ask":
            permission_mode = "ask"
            return CommandResult(message="Bash permission mode set to ask")

        if arg == "auto":
            if not is_sandbox_available():
                return CommandResult(
                    message="Cannot set to 'auto' as no sandbox available."
                )

            permission_mode = "auto"
            return CommandResult(message="Bash permission mode set to auto")

        return CommandResult(message="Usage: /permission [ask|auto]")

    api.register_command(
        SlashCommand(
            name="permission",
            description="View or set bash permission mode: /permission [ask|auto]",
            handler=permission_mode_command_handler,
        )
    )
