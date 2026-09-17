# RPC Requests (stdin from node to python)

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class RequestTypes(StrEnum):
    PROMPT = "prompt"
    STEER = "steer"
    FOLLOW_UP = "follow_up"
    COMPACT = "compact"
    RESUME = "resume"
    REWIND = "rewind"

    ABORT = "abort"
    NEW_SESSION = "new_session"
    GET_STATE = "get_state"
    LIST_SESSIONS = "list_sessions"
    GET_REWIND_TARGETS = "get_rewind_targets"
    GET_COMMANDS = "get_commands"


class BaseRequest(BaseModel):
    id: str | None = None
    type: RequestTypes


class MessageRequest(BaseRequest):
    type: Literal[RequestTypes.PROMPT, RequestTypes.STEER, RequestTypes.FOLLOW_UP]
    message: str


class CompactRequest(BaseRequest):
    type: Literal[RequestTypes.COMPACT] = RequestTypes.COMPACT
    custom_instructions: str | None = None


class ResumeRequest(BaseRequest):
    type: Literal[RequestTypes.RESUME] = RequestTypes.RESUME
    session_id: str


class RewindRequest(BaseRequest):
    type: Literal[RequestTypes.REWIND] = RequestTypes.REWIND
    entry_id: str


# Requests with no arguments other than id and type
class GeneralRequest(BaseRequest):
    type: Literal[
        RequestTypes.ABORT,
        RequestTypes.NEW_SESSION,
        RequestTypes.GET_STATE,
        RequestTypes.LIST_SESSIONS,
        RequestTypes.GET_REWIND_TARGETS,
        RequestTypes.GET_COMMANDS,
    ]


RpcRequest = Annotated[
    MessageRequest | CompactRequest | ResumeRequest | RewindRequest | GeneralRequest,
    Field(discriminator="type"),
]


# RPC Responses (stdout from python to node)
RpcResponseRequestType = RequestTypes | Literal["parse_error"]


class RpcResponse(BaseModel):
    id: str | None = None
    type: Literal["response"] = "response"
    request_type: RpcResponseRequestType
    success: bool
    data: Any = None
    error: str | None = None


rpc_request_adapter: TypeAdapter[RpcRequest] = TypeAdapter(RpcRequest)
