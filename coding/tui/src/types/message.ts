// Port of messages.py in typescript

export interface UserMessageData {
    role: "user";
    content: string;
}

export interface ToolCallData {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
}

export interface AssistantMessageData {
    role: "assistant";
    content: string;
    thinking?: string;
    tool_calls?: ToolCallData[];
}

export interface ToolResultMessageData {
    role: "tool_result";
    tool_name: string;
    tool_call_id: string;
    content: string;
    is_error?: boolean;
}

export type Message = UserMessageData | AssistantMessageData | ToolResultMessageData;