# Truncation

# For now truncation is by bytes
# TODO: Pi has special handling for lines which need more study
# Basically we need to handle case where first line itself is exceeding max_bytes

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_MAX_BYTES = 50 * 1024  # 50 KB (approx 14 K tokens)


@dataclass
class TruncationResult:
    output: str  # content after truncation
    truncated: bool
    total_bytes: int
    output_bytes: int


def truncate(
    content: str,
    truncation_mode: Literal["head", "tail"],
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TruncationResult:
    raw_bytes = content.encode("utf-8")
    total_bytes = len(raw_bytes)

    if total_bytes <= max_bytes:
        return TruncationResult(
            content,
            False,
            total_bytes=total_bytes,
            output_bytes=total_bytes,
        )

    # error = "ignore" will drop any incomplete leading or trailing multi byte char
    # For example emoji take 4 bytes which can get split due to :
    if truncation_mode == "head":
        # Slice first max_bytes
        truncated_content = raw_bytes[:max_bytes].decode("utf-8", errors="ignore")
    else:
        # Slice last max_bytes
        truncated_content = raw_bytes[-max_bytes:].decode("utf-8", errors="ignore")

    return TruncationResult(
        output=truncated_content,
        truncated=True,
        total_bytes=total_bytes,
        output_bytes=len(truncated_content.encode("utf-8")),
    )


# Human readable size
def format_size(bytes_count: int) -> str:
    if bytes_count < 1024:
        return f"{bytes_count}B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count/1024:.1f}KB"
    return f"{bytes_count/(1024*1024):.1f}MB"


# Tool Error
class ToolError(ValueError):
    pass


# Check if path is relative to workspace and resolve it
def default_resolve_path(raw_path: str, cwd: str) -> str:
    workspace = Path(cwd).resolve()
    full_path = (
        workspace / raw_path
    ).resolve()  # Path object handles if 'path' itself start with /

    if full_path != workspace and not full_path.is_relative_to(workspace):
        raise ToolError(f"Path '{raw_path}' is not relative to '{workspace}'")

    return str(full_path)
