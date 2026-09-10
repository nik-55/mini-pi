import { spawn } from "node:child_process";
import readline from "node:readline";

export interface ReadyEvent {
    type: "ready";
    model: string;
}

export interface SessionEvent {
    type: "session";
    session_id: string;
    messages: unknown[];
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

export type AgentEvent =
    | ReadyEvent
    | SessionEvent
    | NoticeEvent
    | ThinkingDeltaEvent
    | TextDeltaEvent
    | ToolExecutionStartEvent
    | ToolExecutionEndEvent
    | AssistantErrorEvent
    | LoopEndEvent;

export function createAgentProcess() {
    const project_root_dir_path = new URL("../../..", import.meta.url).pathname;
    const coding_agent_process = spawn(`${project_root_dir_path}.venv/bin/python`,
        ["-m", "coding.headless"], {
        cwd: project_root_dir_path,
        stdio: ["pipe", "pipe", "inherit"], // stdin (node can write to), stdout (node can read from), stderr (any errors, warnings stream to parent terminal directly)
    });

    const send_msg_to_coding_agent = (msg: Record<string, unknown>) =>
        coding_agent_process.stdin.write(JSON.stringify(msg) + "\n");

    return {
        send: send_msg_to_coding_agent,
        prompt: (text: string) => send_msg_to_coding_agent({ "type": "prompt", "text": text }),
        cancel: () => send_msg_to_coding_agent({ "type": "cancel" }),
        kill: () => coding_agent_process.kill(),
        onEvent: (handler: (event: AgentEvent) => void) => {
            readline.createInterface({ input: coding_agent_process.stdout }).on("line", (line) => {
                try {
                    const event = JSON.parse(line);
                    handler(event);
                } catch {
                    return;
                }
            })
        },
        onExit: (handler: () => void) => {
            coding_agent_process.on("exit", handler);
        },
    }
}
