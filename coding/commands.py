from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


def _normalize_cmd_name(name: str) -> str:
    return name.lstrip("/").strip().lower()


def _parse_command(text: str) -> tuple[str, str]:
    stripped = text.strip()

    if not stripped.startswith("/"):
        return "", ""

    parts = stripped.removeprefix("/").split(maxsplit=1)
    name = parts[0].strip().lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    return name, args


CommandHandler = Callable[["CommandContext"], "CommandResult"]


# We split the command for example /cmd arg1 arg2 into two parts
# One is name=cmd and args="arg1 arg2"


class SlashCommand(BaseModel):
    name: str  # eg: exit, resume
    description: str
    handler: CommandHandler  # Handler to call for this command
    aliases: tuple[str, ...] = Field(default_factory=tuple)  # eg: quit


@dataclass
class CommandContext:
    args: str  # can be empty. Part of command after /cmd
    registry: "CommandRegistry"  # The registry (used by /help to list all commands)


class CommandAction(BaseModel):
    action: Literal["exit", "clear", "resume", "session"]
    args: str | None = None  # part of command after /cmd


class CommandResult(BaseModel):
    is_command: bool = True  # false if input is not a command i.e will be send to agent
    message: str | None = None  # text to shown to user
    action: CommandAction | None = (
        None  # If command perform action, what action to take
    )


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, SlashCommand] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: SlashCommand):
        name = _normalize_cmd_name(command.name)

        if name in self._commands or name in self._aliases:
            raise ValueError(f"Duplicate slash command /{name}")

        self._commands[name] = command

        for alias in command.aliases:
            norm_alias = _normalize_cmd_name(alias)

            if norm_alias in self._aliases or norm_alias in self._commands:
                raise ValueError(f"Duplicate slash command /{norm_alias}")

            self._aliases[norm_alias] = name

    def get(self, name: str) -> SlashCommand | None:
        name = _normalize_cmd_name(name)
        cononical = self._aliases.get(name, None) or name
        return self._commands.get(cononical, None)

    def list_commands(self) -> list[SlashCommand]:
        return sorted(self._commands.values(), key=lambda x: x.name)

    def execute(self, text: str) -> CommandResult:
        name, args = _parse_command(text)

        if not name:
            return CommandResult(is_command=False)

        cmd = self.get(name)

        if cmd is None:
            return CommandResult(
                is_command=True,
                message=f"Unknown command /{name}. Type /help for available commands",
            )

        context = CommandContext(
            args=args,
            registry=self,
        )

        return cmd.handler(context)
