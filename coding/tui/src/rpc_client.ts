import { ChildProcess, spawn } from "node:child_process";
import readline from "node:readline";
import type { AgentEvent } from "./types/events.js";
import type { CompactData, RewindTargetsData, RpcRequest, RpcResponse, SessionData, SessionListData, SessionState } from "./types/rpc.js";

function getPythonBin(): string {
    const project_root_dir_path = new URL("../../..", import.meta.url).pathname;
    const default_local_venv = `${project_root_dir_path}.venv/bin/python`;

    const pythonBin = process.env.MINI_PI_PYTHON || default_local_venv;

    return pythonBin;
}

export class RpcClient {
    private process: ChildProcess;
    private requestId = 0;
    private pendingRequests = new Map<string, { resolve: (resp: RpcResponse) => void; reject: (err: Error) => void }>();
    private eventListeners: Array<(event: AgentEvent) => void> = [];
    private rl: readline.Interface;

    constructor() {
        const pythonBin = getPythonBin();
        // -P ensure python look for modules only at PYTHONPATH 
        this.process = spawn(pythonBin,
            ["-P", "-m", "coding.rpc",], {
            cwd: process.cwd(),
            stdio: ["pipe", "pipe", "inherit"],
            // stdin (node can write to), stdout (node can read from), stderr (any errors, warnings stream to parent terminal directly)
        });

        if (!this.process.stdout) {
            throw new Error("Unable to start python process");
        }

        this.rl = readline.createInterface({ input: this.process.stdout });
        this.rl.on("line", (line) => {
            this.handleLine(line);
        });

        this.process.on("exit", () => {
            const error = new Error("Python process exited");

            for (const pending of this.pendingRequests.values()) {
                pending.reject(error);
            }

            this.pendingRequests.clear();
        });
    }

    private handleLine(line: string): void {
        try {
            const parsed = JSON.parse(line) as (RpcResponse | AgentEvent);
            if (parsed.type == "response") {
                if (parsed.id && this.pendingRequests.has(parsed.id)) {
                    const pending = this.pendingRequests.get(parsed.id)!;
                    this.pendingRequests.delete(parsed.id);
                    pending.resolve(parsed as RpcResponse);
                }
                return;
            }

            for (const listener of this.eventListeners) {
                listener(parsed as AgentEvent);
            }
        }
        catch {
            // Ignore Non JSON lines
        }
    }

    async send<T>(request: RpcRequest): Promise<T> {
        const stdin = this.process.stdin;

        const id = `req_${++this.requestId}`;
        const fullRequest = { ...request, id };

        return new Promise<T>((res, rej) => {
            const timeout = setTimeout(() => {
                this.pendingRequests.delete(id);
                // No race condition as Node run on single thread with "runs to completion"
                rej(new Error(`Timeout waiting for response to ${request.type} with id: ${id}`));
            }, 30000);

            this.pendingRequests.set(id, {
                resolve: (response: RpcResponse) => {
                    clearTimeout(timeout);
                    if (!response.success) {
                        rej(new Error(response.error));
                    }
                    else {
                        res(("data" in response ? response.data : undefined) as T);
                    }
                },
                reject: (err: Error) => {
                    clearTimeout(timeout);
                    rej(err);
                },
            });

            stdin?.write(JSON.stringify(fullRequest) + "\n");
        });
    }

    public onEvent(handler: (event: AgentEvent) => void): () => void {
        this.eventListeners.push(handler);
        const unsubscribe = () => {
            this.eventListeners = this.eventListeners.filter((l) => l != handler);
        }

        return unsubscribe;
    }

    public onExit(handler: () => void): void {
        this.process.on("exit", handler); // on append to list of listerners for "exit"
    }

    public kill(): void {
        this.rl.close();
        this.process.kill();
    }

    // RPC client request interface

    // State
    async getState(): Promise<SessionState> {
        return this.send<SessionState>({ type: "get_state" });
    }

    // Message
    async prompt(message: string): Promise<void> {
        return this.send<void>({ type: "prompt", message });
    }

    async steer(message: string): Promise<void> {
        return this.send<void>({ type: "steer", message });
    }

    async followUp(message: string): Promise<void> {
        return this.send<void>({ type: "follow_up", message });
    }

    // Session
    async newSession(): Promise<SessionData> {
        return this.send<SessionData>({ type: "new_session" });
    }

    async listSessions(): Promise<SessionListData> {
        return this.send<SessionListData>({ type: "list_sessions" });
    }

    async resume(sessionId: string): Promise<SessionData> {
        return this.send<SessionData>({ type: "resume", session_id: sessionId });
    }

    // Rewind
    async rewind(entryId: string): Promise<SessionData> {
        return this.send<SessionData>({ type: "rewind", entry_id: entryId });
    }

    async getRewindTargets(): Promise<RewindTargetsData> {
        return this.send<RewindTargetsData>({ "type": "get_rewind_targets" });
    }

    // Compaction
    async compact(custom_instructions?: string): Promise<CompactData> {
        return this.send<CompactData>({ type: "compact", ...(custom_instructions !== undefined && { custom_instructions }) });
    }

    // Abort
    async abort(): Promise<void> {
        return this.send<void>({ type: "abort" });
    }

}
