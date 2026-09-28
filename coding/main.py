import argparse
import asyncio
from typing import Literal

from coding.modes.cli import run_cli_mode
from coding.modes.rpc import run_rpc_mode, take_over_stdout
from coding.session_factory import build_session_config
from coding.session_runtime import CodingSessionRuntime

AppMode = Literal["cli", "rpc"]


async def main(mode: AppMode) -> None:
    if mode == "rpc":
        # For rpc print during startup go to stderr
        # because print on stdout may break rpc client if not json
        take_over_stdout()

    session_runtime = await CodingSessionRuntime.create(await build_session_config())

    if mode == "rpc":
        await run_rpc_mode(session_runtime)
    else:
        await run_cli_mode(session_runtime)


def run(mode: AppMode) -> None:
    try:
        asyncio.run(main(mode))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["cli", "rpc"])
    args = parser.parse_args()
    run(args.mode)
