// Port of events.py in typescript

import type { Message } from "./message.js";

export interface ReadyEvent {
    type: "ready";
    model: string;
}

export interface SessionEvent {
    type: "session";
    session_id: string;
    messages: Message[];
}

export interface NoticeEvent {
    type: "notice";
    text: string;
}

export interface ThinkingDeltaEvent {
    type: "ThinkingDeltaEvent";
    delta: string;
}

export interface TextDeltaEvent {
    type: "TextDeltaEvent";
    delta: string;
}

export interface ToolExecutionStartEvent {
    type: "ToolExecutionStartEvent";
    tool_name: string;
    arguments?: Record<string, unknown>;
    tool_call_id: string;
}

export interface ToolExecutionEndEvent {
    type: "ToolExecutionEndEvent";
    tool_name: string;
    result: string;
    tool_call_id: string;
    is_error: boolean;
}

export interface AssistantErrorEvent {
    type: "AssistantErrorEvent";
    error: string;
}

export interface LoopEndEvent {
    type: "loop_end";
}


export interface ListSessionRow {
    id: string;
    updated_at: string;
}

export interface ListSessionsEvent {
    type: "sessions",
    rows: ListSessionRow[];
}


export type AgentEvent =
    | ReadyEvent
    | SessionEvent
    | NoticeEvent
    | ThinkingDeltaEvent
    | TextDeltaEvent
    | ToolExecutionStartEvent
    | ToolExecutionEndEvent
    | AssistantErrorEvent
    | LoopEndEvent
    | ListSessionsEvent;
