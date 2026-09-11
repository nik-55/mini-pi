# Built-in command handlers

from coding.commands import (
    CommandAction,
    CommandContext,
    CommandRegistry,
    CommandResult,
    SlashCommand,
)
from coding.extensions.runtime import ExtensionRuntime


def _exit_command_handler(context: CommandContext) -> CommandResult:
    return CommandResult(
        action=CommandAction(action="exit"),
    )


def _clear_command_handler(context: CommandContext) -> CommandResult:
    return CommandResult(
        action=CommandAction(action="clear"),
    )


def _help_command_handler(context: CommandContext) -> CommandResult:
    lines = ["Available slash commands"]

    for cmd in context.registry.list_commands():
        aliases_str = (
            f" (aliases: {', '.join(['/'+a for a in cmd.aliases])})"
            if cmd.aliases
            else ""
        )

        lines.append(f" /{cmd.name}{aliases_str} - {cmd.description}")

    return CommandResult(message="\n".join(lines))


def _session_command_handler(context: CommandContext) -> CommandResult:
    return CommandResult(
        action=CommandAction(
            action="session",
        )
    )


def _resume_command_handler(context: CommandContext) -> CommandResult:
    return CommandResult(
        action=CommandAction(
            action="resume",
            args=context.args,
        )
    )


def build_command_registry(
    extension_runtime: ExtensionRuntime | None = None,
) -> CommandRegistry:
    registry = CommandRegistry()
    default_commands: list[SlashCommand] = [
        SlashCommand(
            name="exit",
            description="Quit the application",
            handler=_exit_command_handler,
            aliases=("quit",),
        ),
        SlashCommand(
            name="clear",
            description="Start a fresh session.",
            handler=_clear_command_handler,
            aliases=("new",),
        ),
        SlashCommand(
            name="help",
            description="List all available slash commands.",
            handler=_help_command_handler,
        ),
        SlashCommand(
            name="session",
            description="Show the active session ID.",
            handler=_session_command_handler,
        ),
        SlashCommand(
            name="resume",
            description="List saved sessions or resume a specific session.",
            handler=_resume_command_handler,
        ),
    ]

    effective_commands = default_commands

    if extension_runtime is not None:
        effective_commands.extend(extension_runtime.get_all_commands())

    for cmd in effective_commands:
        registry.register(cmd)

    return registry
