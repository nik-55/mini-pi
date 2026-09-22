import {
    CombinedAutocompleteProvider,
    Editor,
    Key,
    matchesKey,
    ProcessTerminal,
    TuiMainScreen,
    type SelectItem,
    type SlashCommand,
} from "@earendil-works/pi-tui";

import {
    dim_color_wrapper,
    cyan_color_wrapper,
    red_color_wrapper,
    editorTheme,
} from './theme.js';
import { Trajectory } from "./trajectory.js";
import type { SessionEvent } from "./types/events.js";
import { ActivityLoader } from "./loader.js";
import { TUIHeader } from "./header.js";
import { PickerComponent, type PickerOptions } from "./component.js";
import { RpcClient } from "./rpc_client.js";
import type { ExtensionUIRequest } from "./types/rpc.js";

// UI Setup
const terminal = new ProcessTerminal();
const tui = new TuiMainScreen(terminal);

tui.setClearOnShrink(true);

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
const agent = new RpcClient();

agent.onExit(() => {
    tui.stop();
    process.exit(0);
})

// Initial state fetch
agent.getState().then((state) => {
    tuiHeader.currentModel = state.model;
    tuiHeader.updateHeader();
}).catch((err) => {
    trajectory.addText(`Failed to connect to agent ${err instanceof Error ? err.message : err}`, red_color_wrapper);
})

let activePicker: PickerComponent | null = null;

function showPicker(options: PickerOptions): Promise<SelectItem | null> {
    return new Promise((resolve) => {
        if (activePicker) {
            tui.removeChild(activePicker);
            activePicker = null;
        }

        const picker = new PickerComponent(options);
        activePicker = picker;

        const closePicker = () => {
            tui.removeChild(picker);
            tui.addChild(editor);
            tui.setFocus(editor);
            activePicker = null;
            tui.requestRender();
        }

        picker.onSelect = (item) => {
            closePicker();
            resolve(item);
        }

        picker.onCancel = () => {
            closePicker();
            resolve(null);
        }

        tui.removeChild(editor);
        tui.addChild(picker);
        tui.setFocus(picker);
        tui.requestRender();
    })
}

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
            (async () => {
                try {
                    await agent.followUp(text);
                } catch (err) {
                    trajectory.addText(`Error sending follow up: ${err}`);
                }
            })();
        }
        else {
            trajectory.addText(`steer > ${text}`, cyan_color_wrapper);
            (async () => {
                try {
                    await agent.steer(text);
                } catch (err) {
                    trajectory.addText(`Error sending steering: ${err}`);
                }
            })();
        }
        return;
    }

    if (text == "/clear") {
        (async () => {
            try {
                const data = await agent.newSession();
                currentSessionId = data.session_id;
                trajectory.clear();
                trajectory.addText(`Session started: ${currentSessionId}`, dim_color_wrapper);
            }
            catch (err) {
                trajectory.addText(`Error clearing session: ${err}`, red_color_wrapper);
            }
        })();
        return;
    }

    if (text == "/session") {
        trajectory.addText(`Active session: ${currentSessionId || '(none)'}`);
        return;
    }

    if (text == "/login" || text.startsWith("/login ")) {
        const parts = text.slice("/login".length).trim().split(/\s+/);

        const provider = parts[0];
        const key = parts[1];

        if (!provider || !key) {
            trajectory.addText("Usage: /login <provider> <key>", red_color_wrapper);
            return;
        }

        (async () => {
            try {
                await agent.login(provider, key);
                trajectory.addText(`Saved API key for ${provider}`, dim_color_wrapper);
            } catch (err) {
                trajectory.addText(`Error saving API Key ${err}`, red_color_wrapper);
            }
        })()

        return;
    }

    if (text == "/logout" || text.startsWith("/logout ")) {
        const parts = text.slice("/logout".length).trim().split(/\s+/);

        const provider = parts[0];

        if (!provider) {
            trajectory.addText("Usage: /logout <provider>", red_color_wrapper);
            return;
        }

        (async () => {
            try {
                await agent.logout(provider);
                trajectory.addText(`Removed stored API key for ${provider}`, dim_color_wrapper);
            } catch (err) {
                trajectory.addText(`Error removing API Key ${err}`, red_color_wrapper);
            }
        })()

        return;
    }

    if (text == "/model" || text.startsWith("/model ")) {
        const parts = text.slice("/model".length).trim().split(/\s+/);

        const model_ref = parts[0];

        if (!model_ref) {
            trajectory.addText("Usage: /model <model_ref>", red_color_wrapper);
            return;
        }

        (async () => {
            try {
                await agent.setDefaultModel(model_ref);
                tuiHeader.currentModel = model_ref;
                tuiHeader.updateHeader();
                trajectory.addText(`Set default model to ${model_ref}`, dim_color_wrapper);
            } catch (err) {
                trajectory.addText(`Error setting model to ${err}`, red_color_wrapper);
            }
        })()

        return;
    }


    if (text == "/rewind") {
        (async () => {
            try {
                const data = await agent.getRewindTargets();
                if (data.targets.length == 0) {
                    trajectory.addText("No message to rewind to", dim_color_wrapper);
                    return;
                }

                const items: SelectItem[] = data.targets.map((t) => {
                    const text = t.text.trim() || "(empty message)";
                    const truncated = text.length > 70 ? text.slice(0, 67) + "..." : text;
                    return {
                        value: t.entry_id,
                        label: truncated,
                        description: t.text,
                    }
                })

                const selected = await showPicker({
                    title: "Select message to rewind to",
                    items,
                })
                if (selected) {
                    editor.setText(selected.description ?? "(empty message)");
                    tui.setFocus(editor);
                    tui.requestRender();

                    const rewindData = await agent.rewind(selected.value);
                    currentSessionId = rewindData.session_id;
                    trajectory.loadMessages(rewindData.messages);
                }

            } catch (err) {
                trajectory.addText(`Error rewinding: ${err}`, red_color_wrapper);
            }
        })();
        return;
    }

    if (text.startsWith("/resume")) {
        const id = text.slice("/resume".length).trim();
        (async () => {
            async function resume(id_to_resume: string) {
                const data = await agent.resume(id_to_resume);
                currentSessionId = data.session_id;

                trajectory.loadMessages(data.messages);

                for (const m of data.messages) {
                    if (m.role == "user" && m.content) {
                        editor.addToHistory(m.content);
                    }
                }
                trajectory.addText(`Resumed ${currentSessionId} - ${data.messages.length} messages`, dim_color_wrapper);
            }
            try {

                if (id) {
                    await resume(id);
                } else {
                    const data = await agent.listSessions();
                    if (data.rows.length == 0) {
                        trajectory.addText("No saved sessions", dim_color_wrapper);
                    }
                    else {
                        const items: SelectItem[] = data.rows.map((row) => {
                            const title = row.title || row.id;
                            const label = row.id == currentSessionId ? `${title} (current)` : title;
                            const formattedDate = row.updated_at.split(".")[0]?.replace("T", " ") as string;

                            return {
                                value: row.id,
                                label: label,
                                description: formattedDate,
                            }
                        });

                        const selected = await showPicker({
                            title: 'Select session to resume:',
                            items,
                        })

                        if (selected) {
                            await resume(selected.value);
                        }

                    }
                }
            } catch (err) {

            }
        })();
        return;
    }

    if (text == "/compact" || text.startsWith("/compact ")) {
        const customInstructions = text.slice("/compact".length).trim() || undefined;

        (async () => {
            try {
                await agent.compact(customInstructions);
            } catch (err) {
                trajectory.addText(`Error compacting: ${err}`, red_color_wrapper);
            }
        })();
        return;
    }

    trajectory.addText(`> ${text}`, cyan_color_wrapper);
    (async () => {
        try {
            await agent.prompt(text);
        } catch (err) {
            activityLoader.stop();
            busy = false;
            trajectory.addText(`Error sending prompt: ${err}`);
        }
    })();
}

// Input Handling
editor.onSubmit = (text: string) => {
    return submitInput(text, false);
};

let lastEscTime = 0;
const DOUBLE_ESC_TIMEOUT_MS = 400;

const abortAgent = (async () => {
    try { await agent.abort() } catch (err) {
        trajectory.addText(`Error aborting: ${err}`);
    }
});

tui.addInputListener((data: string) => {
    if (activePicker) {
        if (matchesKey(data, Key.ctrl("c")) || matchesKey(data, Key.esc)) {
            activePicker.onCancel?.();
            return { consume: true }
        }
        return; // Picker will handle rest of key like navigate up / down
    }

    if (matchesKey(data, Key.ctrl("c"))) {
        if (busy) {
            abortAgent();
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
            abortAgent();
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
function handle_coding_agent_event(event: SessionEvent) {
    switch (event.type) {
        case "agent_start": {
            busy = true;
            activityLoader.start("working...")
            break;
        }

        case "message_update": {
            const update = event.assistant_message_event;
            if (update.type == "thinking_delta") {
                trajectory.handleThinkingDelta(update.delta);
            } else if (update.type == "text_delta") {
                trajectory.handleTextDelta(update.delta);
            }
            break;
        }

        case "message_end": {
            if (event.message.role == "assistant") {
                trajectory.handleAssistantMessageEnd(event.message);
            }
            break;
        }

        case "tool_execution_start": {
            trajectory.handleToolStart(event.tool_name, event.tool_call_id, event.arguments);
            break;
        }

        case "tool_execution_end": {
            trajectory.handleToolEnd(event.tool_name, event.tool_call_id, event.result, event.is_error);
            break;
        }

        case "agent_end": {
            activityLoader.stop();
            trajectory.endLoop();
            busy = false;
            break;
        }

        case "compaction_start": {
            busy = true;
            activityLoader.start("compacting...");
            break;
        }

        case "compaction_end": {
            activityLoader.stop();
            busy = false;
            trajectory.handleCompactionEnd(event.result, event.error_message);
            break;
        }

        case "turn_start":
        case "turn_end":
        case "message_start":
            break;
    }
}

agent.onEvent(handle_coding_agent_event);

agent.onExtensionUIRequest(async (req: ExtensionUIRequest) => {
    if (req.payload.method == "select") {
        const selected = await showPicker({
            title: req.payload.title,
            items: req.payload.options.map((opt) => ({
                value: opt,
                label: opt,
            }))
        });

        if (selected) {
            agent.sendExtensionUIResponse({
                type: "extension_ui_response",
                id: req.id,
                value: selected.value,
            });
        } else {
            agent.sendExtensionUIResponse({
                type: "extension_ui_response",
                id: req.id,
                cancelled: true,
            });
        }
    }
    else if (req.payload.method == "notify") {
        trajectory.addText(`[${req.payload.notify_type.toUpperCase()}] ${req.payload.message}`, dim_color_wrapper);
    }
});

const slashCommands: SlashCommand[] = [
    {
        name: "clear", description: "Clear conversation and start new session"
    },
    {
        name: "session", description: "Show active session ID"
    },
    {
        name: "resume", description: "Switch session",
        argumentHint: "<id>"
    },
    { name: "exit", description: "Exit Mini-Pi" },
    {
        name: "rewind", description: "Rewind conversation to a previous user message"
    },
    {
        name: "login", description: "Login to provider using api key", argumentHint: "<provider> <key>"
    },
    {
        name: "logout", description: "Remove the api key for provider", argumentHint: "<provider>"
    },
    {
        name: "model", description: "Set the default model across all sessions", argumentHint: "<model_ref>"
    },
]

editor.setAutocompleteProvider(
    new CombinedAutocompleteProvider(slashCommands, process.cwd(), null)
);

tui.addChild(tuiHeader.headerContainer);
tui.addChild(trajectory.trajectoryContainer);
tui.addChild(editor);

tui.setFocus(editor);
tui.start();
