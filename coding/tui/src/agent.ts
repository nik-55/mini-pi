import { spawn } from "node:child_process";
import readline from "node:readline";
import type { AgentEvent } from "./types/events.js";

function get_python_bin(): string {
    const project_root_dir_path = new URL("../../..", import.meta.url).pathname;
    const default_local_venv = `${project_root_dir_path}.venv/bin/python`;

    const python_bin = process.env.MINI_PI_PYTHON || default_local_venv;

    return python_bin;
}

export function createAgentProcess() {
    const python_bin = get_python_bin();

    const coding_agent_process = spawn(python_bin,
        ["-m", "coding.headless"], {
        cwd: process.cwd(),
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
        resume: (id: string) => send_msg_to_coding_agent({ "type": "resume", "id": id }),
        listSessions: () => send_msg_to_coding_agent({ "type": "list_sessions" }),
    }
}
