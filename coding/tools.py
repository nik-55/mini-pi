# TODO:
# Assumption Agent layer does not validate type
# But here I am assuming that parameter type is validated at agent layer

import asyncio
from pathlib import Path
from typing import Any

from agent.tools import AgentTool


class ToolError(ValueError):
    pass


def _get_path(raw_path: str) -> Path:
    path = Path(raw_path).resolve()
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
                    "description": "Absolute Path to file to read",
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


def create_bash_tool():
    async def execute(arguments: dict[str, Any]) -> str:
        command = arguments.get("command")
        timeout = arguments.get("timeout", None) or 60

        process = await asyncio.create_subprocess_shell(
            command,
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
