from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.tools import AgentTool
from coding.tools.read import default_read_text
from coding.tools.utils import default_resolve_path, ToolError
from coding.tools.write import default_write_text


@dataclass
class EditOperations:
    read_text: Callable[[str], str]
    write_text: Callable[[str, str], None]
    access: Callable[
        [str], None
    ]  # Check if file is accessible and writable (throw error if not)
    resolve_path: Callable[[str, str], str]


def _default_editable_access(path: str) -> None:
    path: Path = Path(path)

    if not path.exists():
        raise ToolError(f"Path '{path}' does not exist")

    if not path.is_file():
        raise ToolError(f"'{path}' is not file")


DEFAULT_EDIT_OPERATIONS = EditOperations(
    read_text=default_read_text,
    write_text=default_write_text,
    access=_default_editable_access,
    resolve_path=default_resolve_path,
)


def create_edit_tool(
    cwd: str,
    operations: EditOperations | None = None,
):
    ops = operations or DEFAULT_EDIT_OPERATIONS

    async def execute(arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path")
        if not raw_path:
            raise ToolError("path is required")

        old_string = arguments.get("old_string")
        new_string = arguments.get("new_string")

        if old_string == "":
            raise ToolError("'old_string' cannot be empty")

        resolved_path = ops.resolve_path(raw_path, cwd)

        ops.access(resolved_path)

        content = ops.read_text(resolved_path)
        count = content.count(old_string)

        if count == 0:
            raise ToolError(f"Could not find old_string in {raw_path}")
        elif count > 1:
            raise ToolError(
                f"Found {count} occurences of old_string in {raw_path}. old_string must have only one occurance"
            )

        new_content = content.replace(old_string, new_string, 1)
        ops.write_text(resolved_path, new_content)

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
