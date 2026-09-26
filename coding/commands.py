# A command is an instruction from the user to our app, as opposed to a message for the model.
# Right now, we can split commands into two categories:
#
# > Built-in commands are handled at the interface layer (CLI or TUI, where the user interacts
# with the app). "Command" is a loose term here, as a built-in command is an action that the
# interface offers, and slash text is just one way to trigger it. The interface can also offer
# a button or key binding to trigger the same action.
# The interface interprets the action and can send a typed action to the session. For example,
# compaction can be triggered by a button. Once the interface interprets that the user wants
# to trigger compaction, it sends a typed action to the session to invoke it. In this file,
# we keep track of supported built-in commands and their descriptions so that every
# interface can implement them.
#
# > Extension commands are handled at the session layer. Currently, they are triggered by slash
# text, and the extension knows how to act on them. The interface does not have any built-in
# handling for them. The interface may send the slash text as a normal prompt, but the session
# can intercept it and interpret it as a command.

from dataclasses import dataclass


# We split the command for example /cmd arg1 arg2 into two parts
# One is name=cmd and args="arg1 arg2"
def parse_command(text: str) -> tuple[str, str]:
    stripped = text.strip()

    if not stripped.startswith("/"):
        return "", ""

    parts = stripped.removeprefix("/").split(maxsplit=1)
    name = parts[0].strip().lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    return name, args


# Since we have split of frontend, and hence the following is imported only by cli.
# TUI define same list in typescript
# However here we defines built in commands supported overall via different interfaces


@dataclass
class BuiltinSlashCommand:
    name: str
    description: str
    argument_hint: str | None = None


BUILTIN_SLASH_COMMANDS: tuple[BuiltinSlashCommand, ...] = (
    BuiltinSlashCommand("exit", "Quit the application"),
    BuiltinSlashCommand("clear", "Start a fresh session"),
    BuiltinSlashCommand("help", "List all available slash commands"),
    BuiltinSlashCommand("session", "Show the active session ID"),
    BuiltinSlashCommand(
        "resume", "List saved sessions or resume a specific session", "<session_id>"
    ),
    BuiltinSlashCommand(
        "compact",
        "Compact conversation history with optional focus instructions",
        "<instructions>",
    ),
    BuiltinSlashCommand("login", "Login to provider using api key", "<provider> <key>"),
    # Cli dont have implementation for following for now
    BuiltinSlashCommand("rewind", "Rewind conversation to a previous user message"),
    BuiltinSlashCommand("logout", "Remove the api key for provider", "<provider>"),
    BuiltinSlashCommand(
        "model", "Set the default model across all sessions", "<model_ref>"
    ),
)
