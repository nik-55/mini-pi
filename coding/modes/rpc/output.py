import json
import sys

from coding.events import SessionEvent
from coding.modes.rpc.types import RpcResponse


_out = sys.stdout  # _out = fd_1


def take_over_stdout() -> None:
    sys.stdout = sys.stderr  # sys.stdout --> fd_2
    # Write to fd_1 i.e out_1 still goes to stdout
    # normal print use sys.stdout so they go to fd_2


def emit(obj: dict):
    _out.write(json.dumps(obj) + "\n")
    _out.flush()


def write_event(event: SessionEvent) -> None:
    emit(event.model_dump(mode="json"))


def send_response(resp: RpcResponse):
    emit(resp.model_dump(mode="json"))
