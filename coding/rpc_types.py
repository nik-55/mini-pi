# RPC Requests (stdin from node to python)

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from ai.types import AgentMessage
from coding.session_manager.manager import ChatSessionFileMetadata
from coding.session import RewindTarget


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
    ]


RpcRequest = Annotated[
    MessageRequest | CompactRequest | ResumeRequest | RewindRequest | GeneralRequest,
    Field(discriminator="type"),
]

rpc_request_adapter: TypeAdapter[RpcRequest] = TypeAdapter(RpcRequest)

# Response Payload
# TODO: Ig we can move most of them in there respective files


class SessionState(BaseModel):
    model: str
    session_id: str | None = None
    session_name: str | None = None


class SessionData(BaseModel):
    session_id: str
    messages: list[AgentMessage] = Field(default_factory=list)


class SessionListData(BaseModel):
    rows: list[ChatSessionFileMetadata]


class RewindTargetsData(BaseModel):
    targets: list[RewindTarget]


class CompactData(BaseModel):
    response: str


# RPC Responses (stdout from python to node)


class BaseRpcResponse(BaseModel):
    id: str | None = None
    type: Literal["response"] = "response"
    request_type: RequestTypes | Literal["parse_error"]
    success: bool


class BaseRpcSuccessResponse(BaseRpcResponse):
    success: Literal[True] = True


# Response with no payload
class EmptySuccessResponse(BaseRpcSuccessResponse):
    request_type: Literal[
        RequestTypes.PROMPT,
        RequestTypes.STEER,
        RequestTypes.FOLLOW_UP,
        RequestTypes.ABORT,
    ]


# Response with Payload
class RpcPayloadResponse(BaseRpcSuccessResponse):
    request_type: Literal[
        RequestTypes.GET_STATE,
        RequestTypes.NEW_SESSION,
        RequestTypes.COMPACT,
        RequestTypes.LIST_SESSIONS,
        RequestTypes.RESUME,
        RequestTypes.GET_REWIND_TARGETS,
        RequestTypes.REWIND,
    ]
    data: SessionState | SessionData | CompactData | SessionListData | RewindTargetsData


class RpcErrorResponse(BaseRpcResponse):
    success: Literal[False] = False
    error: str


RpcResponse = EmptySuccessResponse | RpcPayloadResponse | RpcErrorResponse
