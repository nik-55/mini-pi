import { spawn } from "node:child_process";
import readline from "node:readline";

export function createAgentProcess() {
    const project_root_dir_path = new URL("../..", import.meta.url).pathname;
    const coding_agent_process = spawn(`${project_root_dir_path}.venv/bin/python`,
        ["-m", "coding.headless"], {
        cwd: project_root_dir_path,
        stdio: ["pipe", "pipe", "inherit"], // stdin (node can write to), stdout (node can read from), stderr (any errors, warnings stream to parent terminal directly)
    });

    const send_msg_to_coding_agent = (msg) =>
        coding_agent_process.stdin.write(JSON.stringify(msg) + "\n");

    return {
        send: send_msg_to_coding_agent,
        prompt: (text) => send_msg_to_coding_agent({ "type": "prompt", "text": text }),
        cancel: () => send_msg_to_coding_agent({ "type": "cancel" }),
        kill: () => coding_agent_process.kill(),
        onEvent: (handler) => {
            readline.createInterface({ input: coding_agent_process.stdout }).on("line", (line) => {
                try {
                    const event = JSON.parse(line);
                    handler(event);
                } catch {
                    return;
                }
            })
        },
        onExit: (handler) => {
            coding_agent_process.on("exit", handler);
        },
    }
}
