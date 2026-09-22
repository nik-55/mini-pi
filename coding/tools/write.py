from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.tools import AgentTool
from coding.tools.utils import default_resolve_path
from coding.tools.utils import ToolError


@dataclass
class WriteOperations:
    write_text: Callable[[str, str], None]
    access: Callable[
        [str], None
    ]  # Check if file is accessible and writable (throw error if not)
    resolve_path: Callable[[str, str], str]


def _default_writable_access(path: str) -> None:
    path: Path = Path(path)

    if path.exists() and not path.is_file():
        raise ToolError(f"'{path}' exist and is not a file")


def default_write_text(path: str, content: str):
    path: Path = Path(path)
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(content, encoding="utf-8")


DEFAULT_WRITE_OPERATIONS = WriteOperations(
    write_text=default_write_text,
    access=_default_writable_access,
    resolve_path=default_resolve_path,
)


def create_write_tool(
    cwd: str,
    operations: WriteOperations | None = None,
):
    ops = operations or DEFAULT_WRITE_OPERATIONS

    async def execute(arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path")

        if not raw_path:
            raise ToolError("path is required")

        content = arguments.get("content")

        resolved_path = ops.resolve_path(raw_path, cwd)

        ops.access(resolved_path)
        ops.write_text(resolved_path, content)
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
