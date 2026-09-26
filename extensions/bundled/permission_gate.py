from typing import Literal

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

    def permission_mode_command_handler(args: str, context: ExtensionContext) -> None:
        global permission_mode

        if context.ui is None:
            # No one to notify better not to change
            return

        arg = args.strip().lower() if args else None

        if not arg:
            sandbox_status = "available" if is_sandbox_available() else "unavailable"
            context.ui.notify(
                message=f"Current bash permission mode '{permission_mode}' (sandbox: {sandbox_status})"
            )
            return

        if arg == "ask":
            permission_mode = "ask"
            context.ui.notify(message="Bash permission mode set to ask")
            return

        if arg == "auto":
            if not is_sandbox_available():
                context.ui.notify(
                    message="Cannot set to 'auto' as no sandbox available."
                )
                return

            permission_mode = "auto"
            context.ui.notify(message="Bash permission mode set to auto")
            return

        context.ui.notify(message="Usage: /permission [ask|auto]")
        return

    api.register_command(
        name="permission",
        description="View or set bash permission mode: /permission [ask|auto]",
        handler=permission_mode_command_handler,
    )
