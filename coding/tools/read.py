from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.tools import AgentTool
from coding.tools.utils import (
    ToolError,
    default_resolve_path,
    format_size,
    truncate,
)


@dataclass
class ReadOperations:
    read_text: Callable[[str], str]
    access: Callable[
        [str], None
    ]  # Check if file is accessible and readable (throw error if not)
    resolve_path: Callable[
        [str, str], str
    ]  # resolve path relative to workspace (throw error if not relative)


def _default_readable_access(path: str) -> None:
    path: Path = Path(path)

    if not path.exists():
        raise ToolError(f"Path '{path}' does not exist")

    if not path.is_file():
        raise ToolError(f"'{path}' is not file")


def default_read_text(path: str) -> str:
    path: Path = Path(path)
    return path.read_text(encoding="utf-8")


DEFAULT_READ_OPERATIONS = ReadOperations(
    read_text=default_read_text,
    access=_default_readable_access,
    resolve_path=default_resolve_path,
)


def create_read_tool(
    cwd: str,
    operations: ReadOperations | None = None,
):
    ops = operations or DEFAULT_READ_OPERATIONS

    async def execute(arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path")
        if not raw_path:
            raise ToolError("path is required")

        offset = arguments.get("offset", None) or 1
        limit = arguments.get("limit", None)

        resolved_path = ops.resolve_path(raw_path, cwd)

        ops.access(resolved_path)
        content = ops.read_text(resolved_path)

        # Empty content
        if not content:
            return ""

        lines = content.splitlines()
        total_lines = len(lines)

        if offset > total_lines:
            raise ToolError(
                f"Offset {offset} is beyond end of file ({total_lines}) lines total"
            )

        start_index = offset - 1
        if limit is not None:
            selected_lines = lines[start_index : start_index + limit]
        else:
            selected_lines = lines[start_index:]

        selected_text = "\n".join(selected_lines)
        truncated = truncate(selected_text, "head")
        output = truncated.output

        output_lines = output.splitlines()
        output = "\n".join(
            f"{i}. {l}" for i, l in enumerate(output_lines, start=offset)
        )

        if truncated.truncated:
            output += (
                f"\n\n[Showing first {format_size(truncated.output_bytes)}] "
                f"of {format_size(truncated.total_bytes)}. "
                f"Use offset to read subsequent lines. Last line may be partial]"
            )

        return output

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
