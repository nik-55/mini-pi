import {
    Container,
    Editor,
    Key,
    matchesKey,
    ProcessTerminal,
    Spacer,
    Text,
    TuiMainScreen,
} from "@earendil-works/pi-tui";

import {
    dim_color_wrapper,
    cyan_color_wrapper,
    red_color_wrapper,
    magneta_color_wrapper,
    editorTheme,
} from './theme.js';
import { MessageComponent, CollapsibleComponent } from "./component.js";
import { summarizeArgs } from './formatters.js';
import { createAgentProcess } from "./agent.js";

// UI Setup
const terminal = new ProcessTerminal();
const tui = new TuiMainScreen(terminal);

const trajectoryContainer = new Container();
const editor = new Editor(tui, editorTheme, {
    paddingX: 1
});

function addBlock(component) {
    trajectoryContainer.addChild(component);
    trajectoryContainer.addChild(new Spacer(1));
    tui.requestRender();
}

function addText(text, color) {
    addBlock(new Text(color ? color(text) : text, 1, 0));
}

// State
let busy = false;
let expanded = false;
const collapsibles = [];
const tools_to_component_mapping = new Map();
let currentAssistantMessageComponent = null;
let currentThinkingBlock = null;


function createCollapsible(header, color) {
    const block = new CollapsibleComponent(header, color);
    block.setExpanded(expanded);
    collapsibles.push(block);
    addBlock(block);
    return block;
}


function toggleAllCollapsibles() {
    expanded = !expanded;
    for (const block of collapsibles) {
        block.setExpanded(expanded);
    }

    tui.requestRender();
}


function finishThinking() {
    if (currentThinkingBlock != null) {
        currentThinkingBlock.header = "Thought";
        currentThinkingBlock.sync();
        currentThinkingBlock = null;
    }
}

// Agent
const agent = createAgentProcess();

agent.onExit(() => {
    tui.stop();
    process.exit(0);
})

// Input Handling
editor.onSubmit = (text) => {
    text = text.trim();
    if (!text) return;

    editor.setText("");

    if (text == "/exit") {
        agent.kill();
        tui.stop();
        process.exit(0);
    }

    if (busy) return;

    addText(`user> ${text}`, cyan_color_wrapper);
    agent.prompt(text);
    busy = true;
};


tui.addInputListener((data) => {
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
        toggleAllCollapsibles();
        return { consume: true };
    }
});

// Agent Event Handler
function handle_coding_agent_event(event) {
    switch (event.type) {
        case "ready": {
            addText(`mini-pi (${event.model})`, dim_color_wrapper);
            break;
        }

        case "session": {
            addText(`Session started: ${event.session_id}`, dim_color_wrapper);
            break;
        }

        case "notice": {
            addText(event.text, dim_color_wrapper);
            break;
        }

        case "ThinkingDeltaEvent": {
            if (currentThinkingBlock == null) {
                currentThinkingBlock = createCollapsible("Thinking...", dim_color_wrapper);
            }
            currentThinkingBlock.text += event.delta;
            currentThinkingBlock.sync();
            tui.requestRender();
            break;
        }

        case "TextDeltaEvent": {
            finishThinking();
            if (currentAssistantMessageComponent == null) {
                currentAssistantMessageComponent = new MessageComponent();
                addBlock(currentAssistantMessageComponent);
            }
            currentAssistantMessageComponent.append(event.delta);
            tui.requestRender();
            break;
        }


        case "ToolExecutionStartEvent": {
            finishThinking();
            currentAssistantMessageComponent = null;

            const block = createCollapsible(`${event.tool_name}(${summarizeArgs(event.arguments ?? {})})`, magneta_color_wrapper)

            block.detail = JSON.stringify(event.arguments, null, 2);
            block.sync();
            tools_to_component_mapping.set(event.tool_call_id, block);
            tui.requestRender();
            break;
        }

        case "ToolExecutionEndEvent": {
            const block = tools_to_component_mapping.get(event.tool_call_id) ?? createCollapsible(event.tool_name, magneta_color_wrapper);

            block.text = event.result;
            block.color = event.is_error ? red_color_wrapper : magneta_color_wrapper;
            block.sync()
            tui.requestRender();
            break;
        }

        case "AssistantErrorEvent": {
            finishThinking();
            currentAssistantMessageComponent = null;

            addText(`Error: ${event.error}`, red_color_wrapper);
            break;
        }

        case "loop_end": {
            finishThinking();
            currentAssistantMessageComponent = null;
            busy = false;
            break;
        }
    }
}

agent.onEvent(handle_coding_agent_event);

tui.addChild(trajectoryContainer);
tui.addChild(editor);

tui.setFocus(editor);
tui.start();
