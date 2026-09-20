import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Any

from agent.cancellation import CancellationSignal
from agent.tools import AgentTool
from coding.tools.utils import ToolError, format_size, truncate


@dataclass
class ExecResult:
    output: str
    exit_code: int | None
    timed_out: bool = False
    cancelled: bool = False


@dataclass
class BashOperations:
    exec: Callable[
        [str, str, float, CancellationSignal | None],
        Awaitable[ExecResult],
    ]


async def _default_exec(
    command: str,
    cwd: str,
    timeout: float,
    signal: CancellationSignal | None,
) -> ExecResult:
    if shutil.which("bwrap") is None:
        raise ToolError("Bash is not available")

    argv = bwrap_argv(
        home=Path.home(),
        workspace=Path(cwd).resolve(),
        command=command,
    )

    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    communication_task = asyncio.create_task(process.communicate())
    cancel_signal_task = asyncio.create_task(signal.wait()) if signal else None

    wait_set = {communication_task}

    if cancel_signal_task is not None:
        wait_set.add(cancel_signal_task)

    output = ""
    timed_out = False
    cancelled = False

    try:
        done, _ = await asyncio.wait(
            wait_set,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Timeout occurs when nothing is done
        if not done:
            timed_out = True
        elif cancel_signal_task is not None and cancel_signal_task in done:
            # If communication task is in done process is already completed
            if communication_task not in done:
                cancelled = True

        if not timed_out and not cancelled:
            stdout, _ = communication_task.result()
            output = stdout.decode("utf-8", errors="replace")
    finally:
        # Cleanup
        if process.returncode is None:
            # process still alive
            # task.cancel only kill python task not os process
            process.kill()
            await process.wait()

        if cancel_signal_task is not None and not cancel_signal_task.done():
            cancel_signal_task.cancel()

        if not communication_task.done():
            communication_task.cancel()

    return ExecResult(
        output=output,
        timed_out=timed_out,
        cancelled=cancelled,
        exit_code=process.returncode,
    )


DEFAULT_BASH_OPERATIONS = BashOperations(
    exec=_default_exec,
)


# TODO: Should cwd be str or list[str]
def create_bash_tool(
    cwd: str,
    operations: BashOperations | None = None,
):
    ops = operations or DEFAULT_BASH_OPERATIONS

    async def execute(
        arguments: dict[str, Any],
        signal: CancellationSignal | None = None,
    ) -> str:
        command = arguments.get("command")
        timeout = float(arguments.get("timeout", None) or 60)

        if not command:
            raise ToolError("command is required")

        result = await ops.exec(command, cwd, timeout, signal)

        if result.timed_out:
            return f"Error: Command timed out after {timeout} seconds"
        if result.cancelled:
            return f"Error: Command Cancelled by user"

        stdout = result.output or "(no output)"

        truncated = truncate(stdout, "tail")
        output = truncated.output

        if truncated.truncated:
            # TODO: Write to temp file using write_text operation
            output += (
                f"\n\n[Showing last {format_size(truncated.output_bytes)} "
                f"of {format_size(truncated.total_bytes)}.]"
            )

        if result.exit_code != 0 and result.exit_code is not None:
            output += f"\n[Process exited with code {result.exit_code}]"

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
