from coding.extensions.api import (
    ExtensionAPI,
    InputHookPayload,
    InputHookResult,
    ToolCallHookPayload,
    ToolCallHookResult,
)


def setup(api: ExtensionAPI):
    @api.on("input")
    def on_input(payload: InputHookPayload):
        if payload.text.strip() == "@ping":
            return InputHookResult(
                action="transform", text="Reply with exact word: MiniPI_PONG"
            )

    @api.on("tool_call")
    def on_tool(payload: ToolCallHookPayload):
        if payload.tool_name == "bash":
            cmd = payload.arguments.get("command", None) or ""

            if cmd.strip() == "whoami":
                return ToolCallHookResult(block=True, reason="I am MINI PI")
