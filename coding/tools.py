# TODO:
# Assumption Agent layer does not validate type
# But here I am assuming that parameter type is validated at agent layer

import asyncio
import os
from pathlib import Path
import shutil
from typing import Any

from agent.tools import AgentTool


class ToolError(ValueError):
    pass


def _get_home() -> Path:
    return Path.home()


def _get_workspace() -> Path:
    return Path.cwd().resolve()


def _get_path(raw_path: str) -> Path:
    workspace = _get_workspace()
    path = (workspace / raw_path).resolve()
    if path != workspace and not path.is_relative_to(workspace):
        raise ToolError(f"Path '{raw_path}' is not relative to '{workspace}'")
    return path


def create_read_tool():
    async def execute(arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path")
        start = (arguments.get("offset", None) or 1) - 1
        limit = arguments.get("limit", None) or 300

        path = _get_path(raw_path)
        if not path.exists():
            raise ToolError(f"Path '{raw_path}' does not exist")

        if path.is_dir():
            raise ToolError(f"'{raw_path}' is a dir")

        file_text = path.read_text(encoding="utf-8")
        lines = file_text.splitlines()[start : start + limit]

        return "\n".join([f"{i}. {l}" for i, l in enumerate(lines, start=start + 1)])

    return AgentTool(
        name="read",
        description=(
            "Read the contents of a text file with offset and limit for line ranges"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (1-indexed)",
                },
                "limit": {"type": "integer", "description": "Number of lines to read"},
            },
            "required": ["path"],
        },
        execute_fn=execute,
    )


def create_write_tool():
    async def execute(arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path")
        content = arguments.get("content")

        path = _get_path(raw_path)
        path.parent.mkdir(exist_ok=True, parents=True)

        path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to '{raw_path}'"

    return AgentTool(
        name="write",
        description="Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
        execute_fn=execute,
    )


def create_edit_tool():
    async def execute(arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path")
        old_string = arguments.get("old_string")
        new_string = arguments.get("new_string")

        if old_string == "":
            raise ToolError("'old_string' cannot be empty")

        path = _get_path(raw_path)

        if not path.exists():
            raise ToolError(f"Path '{raw_path}' does not exist")

        if path.is_dir():
            raise ToolError(f"'{raw_path}' is a dir")

        content = path.read_text(encoding="utf-8")
        count = content.count(old_string)

        if count == 0:
            raise ToolError(f"Could not find old_string in {raw_path}")
        elif count > 1:
            raise ToolError(
                f"Found {count} occurences of old_string in {raw_path}. old_string must have only one occurance"
            )

        new_content = content.replace(old_string, new_string, 1)
        path.write_text(new_content, encoding="utf-8")

        return f"Successfully edited '{raw_path}'"

    return AgentTool(
        name="edit",
        description="Edit a file by replacing an exact unique occurrence of old_string with new_string.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact string to find and replace. Must match uniquely.",
                },
                "new_string": {
                    "type": "string",
                    "description": "String to replace old_string with",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
        execute_fn=execute,
    )


def create_bash_tool():
    async def execute(arguments: dict[str, Any]) -> str:
        if shutil.which("bwrap") is None:
            raise ToolError("Bash is not available")

        command = arguments.get("command")
        timeout = arguments.get("timeout", None) or 60

        argv = bwrap_argv(home=_get_home(), workspace=_get_workspace(), command=command)

        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")
        except TimeoutError:
            process.kill()
            await process.wait()
            return f"Error: Command timed out after '{timeout}' seconds"

        output = output or "(no output)"
        if process.returncode != 0:
            output += f"\n[Process exited with code {process.returncode}]"

        return output

    return AgentTool(
        name="bash",
        description="Execute shell command. Returns stdout and stderr.",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "number",
                    "description": "Optional timeout in seconds (default: 60)",
                },
            },
            "required": ["command"],
        },
        execute_fn=execute,
    )


# Only works on linux with bwrap
def bwrap_argv(home: Path, workspace: Path, command: str) -> list[str]:
    return [
        "bwrap",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind-try",
        "/bin",
        "/bin",
        "--ro-bind-try",
        "/sbin",
        "/sbin",
        "--ro-bind-try",
        "/lib",
        "/lib",
        "--ro-bind-try",
        "/lib64",
        "/lib64",
        "--ro-bind-try",
        "/etc",
        "/etc",
        "--ro-bind-try",
        "/run/systemd/resolve",
        "/run/systemd/resolve",
        "--ro-bind",
        str(home),
        str(home),
        "--tmpfs",
        str(home / ".cache"),
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(workspace),
        str(workspace),
        "--chdir",
        str(workspace),
        "--unshare-all",
        "--share-net",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--setenv",
        "HOME",
        str(home),
        "--setenv",
        "PATH",
        os.environ.get("PATH", f"{home}/.local/bin:/usr/local/bin:/usr/bin:/bin"),
        "--setenv",
        "TERM",
        "dumb",
        "--",
        "/bin/sh",
        "-c",
        command,
    ]
