import {
    Editor,
    Key,
    matchesKey,
    ProcessTerminal,
    TuiMainScreen,
} from "@earendil-works/pi-tui";

import {
    dim_color_wrapper,
    cyan_color_wrapper,
    red_color_wrapper,
    editorTheme,
} from './theme.js';
import { createAgentProcess } from "./agent.js";
import { Trajectory } from "./trajectory.js";
import type { AgentEvent } from "./types/events.js";
import { ActivityLoader } from "./loader.js";

// UI Setup
const terminal = new ProcessTerminal();
const tui = new TuiMainScreen(terminal);

const editor = new Editor(tui, editorTheme, {
    paddingX: 1
});
const trajectory = new Trajectory(() => tui.requestRender());
const activityLoader = new ActivityLoader(tui, editor);

// State
let busy: boolean = false;
let currentSessionId: string = "";

// Agent
const agent = createAgentProcess();

agent.onExit(() => {
    tui.stop();
    process.exit(0);
})

// Input Handling
editor.onSubmit = (text: string) => {
    text = text.trim();
    if (!text) return;

    editor.setText("");

    if (text == "/exit") {
        agent.kill();
        tui.stop();
        process.exit(0);
    }

    if (busy) return;

    if (text == "/clear") {
        agent.send({ "type": "new_session" });
        return;
    }

    if (text == "/session") {
        trajectory.addText(`Active session: ${currentSessionId}`);
        return;
    }

    if (text.startsWith("/resume")) {
        const id = text.slice("/resume".length).trim();
        if (id) {
            agent.resume(id);
        } else {
            agent.listSessions();
        }

        return;
    }

    activityLoader.start("working...")
    trajectory.addText(`> ${text}`, cyan_color_wrapper);
    agent.prompt(text);
    busy = true;
};


tui.addInputListener((data: string) => {
    if (matchesKey(data, Key.ctrl("c")) || matchesKey(data, Key.esc)) {
        if (busy) {
            agent.cancel();
            return { consume: true }; // Ctrl+c is being consumed, dont passes down
        } else {
            agent.kill();
            tui.stop();
            process.exit(0);
        }
    }

    else if (matchesKey(data, Key.ctrl("o"))) {
        trajectory.toggleAllCollapsibles();
        return { consume: true };
    }
});

// Agent Event Handler
function handle_coding_agent_event(event: AgentEvent) {
    switch (event.type) {
        case "ready": {
            trajectory.addText(`mini-pi (${event.model})`, dim_color_wrapper);
            break;
        }

        case "session": {
            currentSessionId = event.session_id;

            if (event.messages.length > 0) {
                trajectory.loadMessages(event.messages);
                trajectory.addText(`Resumed ${currentSessionId} - ${event.messages.length} messages`, dim_color_wrapper);
            } else {
                trajectory.clear();
                trajectory.addText(`Session started: ${event.session_id}`, dim_color_wrapper);
            }
            break;
        }

        case "notice": {
            trajectory.addText(event.text, dim_color_wrapper);
            break;
        }

        case "ThinkingDeltaEvent": {
            trajectory.handleThinkingDelta(event.delta);
            break;
        }

        case "TextDeltaEvent": {
            trajectory.handleTextDelta(event.delta);
            break;
        }

        case "ToolExecutionStartEvent": {
            trajectory.handleToolStart(event.tool_name, event.tool_call_id, event.arguments);
            break;
        }

        case "ToolExecutionEndEvent": {
            trajectory.handleToolEnd(event.tool_name, event.tool_call_id, event.result, event.is_error);
            break;
        }

        case "AssistantErrorEvent": {
            activityLoader.stop();
            trajectory.endLoop();
            trajectory.addText(`Error: ${event.error}`, red_color_wrapper);
            break;
        }

        case "loop_end": {
            activityLoader.stop();
            trajectory.endLoop();
            busy = false;
            break;
        }

        case "sessions": {
            if (event.rows.length == 0) {
                trajectory.addText("No saved sessions", dim_color_wrapper);
            }
            else {
                const lines = ["Saved Sessions:"];
                for (const row of event.rows.slice(0, 15)) {
                    lines.push(`    ${row.updated_at} ${row.id}`);
                }
                lines.push("use /resume <id> to switch");
                trajectory.addText(lines.join("\n"), dim_color_wrapper);
            }
            break;
        }
    }
}

agent.onEvent(handle_coding_agent_event);

tui.addChild(trajectory.trajectoryContainer);
tui.addChild(editor);

tui.setFocus(editor);
tui.start();
