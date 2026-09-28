# JSON RPC 2.0 - https://www.jsonrpc.org/specification

from coding.modes.rpc.rpc import run_rpc_mode
from coding.modes.rpc.output import take_over_stdout

__all__ = [
    "run_rpc_mode",
    "take_over_stdout",
]
