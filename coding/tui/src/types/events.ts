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

export interface AssistantDoneEvent {
    type: "AssistantDoneEvent",
    message: Message,
}

export interface LoopEndEvent {
    type: "loop_end";
}


export interface ListSessionRow {
    id: string;
    updated_at: string;
    title?: string | null;
}

export interface ListSessionsEvent {
    type: "sessions",
    rows: ListSessionRow[];
}

export interface RewindTargetRow {
    entry_id: string;
    text: string;
}

export interface RewindTargetsEvent {
    type: "rewind_targets";
    targets: RewindTargetRow[];
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
    | AssistantDoneEvent
    | LoopEndEvent
    | ListSessionsEvent
    | RewindTargetsEvent;
