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
import { TUIHeader } from "./header.js";

// UI Setup
const terminal = new ProcessTerminal();
const tui = new TuiMainScreen(terminal);

const editor = new Editor(tui, editorTheme, {
    paddingX: 1
});
const trajectory = new Trajectory(() => tui.requestRender());
const tuiHeader = new TUIHeader(() => tui.requestRender());
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

function submitInput(text: string, isFollowup: boolean = false) {
    text = text.trim();
    if (!text) return;

    editor.addToHistory(text);

    editor.setText("");

    if (text == "/exit") {
        agent.kill();
        tui.stop();
        process.exit(0);
    }

    if (busy) {
        if (isFollowup) {
            trajectory.addText(`follow-up > ${text}`, cyan_color_wrapper);
            agent.follow_up(text);
        }
        else {
            trajectory.addText(`steer > ${text}`, cyan_color_wrapper);
            agent.steer(text);
        }
        return;
    }

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
}

// Input Handling
editor.onSubmit = (text: string) => {
    return submitInput(text, false);
};

let lastEscTime = 0;
const DOUBLE_ESC_TIMEOUT_MS = 400;

tui.addInputListener((data: string) => {
    if (matchesKey(data, Key.ctrl("c"))) {
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

    else if (matchesKey(data, Key.alt("enter"))) {
        const text = editor.getText().trim();
        submitInput(text, true);
        return { consume: true };
    }

    else if ((matchesKey(data, Key.esc))) {
        if (busy) {
            agent.cancel();
            return { consume: true };
        }

        if (editor.isShowingAutocomplete()) {
            return; // Editor will handle auto complete request
        }

        const now = Date.now();
        if (now - lastEscTime <= DOUBLE_ESC_TIMEOUT_MS) {
            editor.setText("");
            lastEscTime = 0;
        }
        else {
            lastEscTime = now;
        }

        return { consume: true };
    }
});

// Agent Event Handler
function handle_coding_agent_event(event: AgentEvent) {
    switch (event.type) {
        case "ready": {
            tuiHeader.currentModel = event.model;
            tuiHeader.updateHeader();
            break;
        }

        case "session": {
            currentSessionId = event.session_id;

            if (event.messages.length > 0) {
                trajectory.loadMessages(event.messages);

                for (const m of event.messages) {
                    if (m.role == "user" && m.content) {
                        editor.addToHistory(m.content);
                    }
                }
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

        case "AssistantDoneEvent": {
            trajectory.finishThinking();
            trajectory.currentAssistantMarkdownMsgComponent = null;
            trajectory.addSpacer(1);
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

tui.addChild(tuiHeader.headerContainer);
tui.addChild(trajectory.trajectoryContainer);
tui.addChild(editor);

tui.setFocus(editor);
tui.start();
