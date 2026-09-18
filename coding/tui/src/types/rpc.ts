import type { Message } from "./message.js";

// RPC Client Request
export interface MessageRequest {
    id?: string;
    type: "prompt" | "steer" | "follow_up";
    message: string;
}

export interface CompactRequest {
    id?: string;
    type: "compact";
    custom_instructions?: string;
}

export interface ResumeRequest {
    id?: string;
    type: "resume";
    session_id: string;
}

export interface RewindRequest {
    id?: string;
    type: "rewind";
    entry_id: string;
}

// No arguments
export interface GeneralRequest {
    id?: string;
    type:
    | "abort"
    | "new_session"
    | "get_state"
    | "list_sessions"
    | "get_rewind_targets"
    | "get_commands";
}

export type RpcRequest =
    | MessageRequest
    | CompactRequest
    | ResumeRequest
    | RewindRequest
    | GeneralRequest;

// RPC server response payload
export interface SessionState {
    model: string;
    session_id?: string;
    session_name?: string | null;
}

export interface SessionData {
    session_id: string;
    messages: Message[];
}

export interface ChatSessionFileMetadata {
    id: string;
    updated_at: string;
    title?: string | null;
}

export interface SessionListData {
    rows: ChatSessionFileMetadata[];
}

export interface RewindTarget {
    entry_id: string;
    text: string;
}

export interface RewindTargetsData {
    targets: RewindTarget[];
}

export interface CompactData {
    response: string;
}

// RPC Server Response

export type RpcSuccessResponse =
    | { id?: string; type: "response"; request_type: "prompt" | "steer" | "follow_up" | "abort"; success: true; }
    | { id?: string; type: "response"; request_type: "get_state"; success: true; data: SessionState; }
    | { id?: string; type: "response"; request_type: "new_session"; success: true; data: SessionData; }
    | { id?: string; type: "response"; request_type: "compact"; success: true; data: CompactData; }
    | { id?: string; type: "response"; request_type: "list_sessions"; success: true; data: SessionListData; }
    | { id?: string; type: "response"; request_type: "resume"; success: true; data: SessionData; }
    | { id?: string; type: "response"; request_type: "rewind"; success: true; data: SessionData; }
    | { id?: string; type: "response"; request_type: "get_rewind_targets"; success: true; data: RewindTargetsData; };

export interface RpcErrorResponse {
    id?: string;
    type: "response";
    request_type: string;
    success: false;
    error: string;
};

export type RpcResponse = RpcSuccessResponse | RpcErrorResponse;
