import { Container, Spacer, Text, type Component } from "@earendil-works/pi-tui";
import { cyan_color_wrapper, dim_color_wrapper, magneta_color_wrapper, red_color_wrapper, type Colorfn } from "./theme.js";
import { CollapsibleComponent, MarkdownMsgComponent } from "./component.js";
import { summarizeArgs } from "./formatters.js";
import type { Message } from "./types/message.js";

export class Trajectory {
    public trajectoryContainer = new Container();
    public requestRender: () => void;
    public currentThinkingBlock: CollapsibleComponent | null = null;
    public expanded: boolean = false;
    public collapsibles: CollapsibleComponent[] = [];
    public currentAssistantMarkdownMsgComponent: MarkdownMsgComponent | null = null;
    public tools_to_component_mapping: Map<string, CollapsibleComponent> = new Map();

    constructor(requestRender: () => void) {
        this.requestRender = requestRender;
    }

    public addBlock(component: Component) {
        this.trajectoryContainer.addChild(component);
        this.requestRender();
    }

    public addSpacer(lines: number) {
        this.trajectoryContainer.addChild(new Spacer(lines));
    }

    public addText(text: string, color?: Colorfn) {
        this.addBlock(new Text(color ? color(text) : text, 1, 0));
    }

    public finishThinking() {
        if (this.currentThinkingBlock != null) {
            this.currentThinkingBlock.header = "Thought";
            this.currentThinkingBlock.sync();
            this.currentThinkingBlock = null;
        }
    }

    public createCollapsible(header: string, color: Colorfn): CollapsibleComponent {
        const block = new CollapsibleComponent(header, color);
        block.setExpanded(this.expanded);
        this.collapsibles.push(block);
        this.addBlock(block);
        return block;
    }


    public toggleAllCollapsibles() {
        this.expanded = !this.expanded;
        for (const block of this.collapsibles) {
            block.setExpanded(this.expanded);
        }

        this.requestRender();
    }

    public handleThinkingDelta(delta: string) {
        if (this.currentThinkingBlock == null) {
            this.currentThinkingBlock = this.createCollapsible("Thinking...", dim_color_wrapper);
        }
        this.currentThinkingBlock.text += delta;
        this.currentThinkingBlock.sync();
        this.requestRender();
    }

    public handleTextDelta(delta: string) {
        this.finishThinking();
        if (this.currentAssistantMarkdownMsgComponent == null) {
            this.currentAssistantMarkdownMsgComponent = new MarkdownMsgComponent();
            this.addBlock(this.currentAssistantMarkdownMsgComponent);
        }
        this.currentAssistantMarkdownMsgComponent.append(delta);
        this.requestRender();
    }

    public handleToolStart(name: string, tool_call_id: string, args?: Record<string, unknown>) {
        this.finishThinking();
        this.currentAssistantMarkdownMsgComponent = null;

        const block = this.createCollapsible(`${name}(${summarizeArgs(args ?? {})})`, magneta_color_wrapper)

        block.detail = JSON.stringify(args, null, 2);
        block.sync();
        this.tools_to_component_mapping.set(tool_call_id, block);
        this.requestRender();
    }

    public handleToolEnd(name: string, tool_call_id: string, result: string, is_error: boolean) {
        const block = this.tools_to_component_mapping.get(tool_call_id);
        if (block) {
            block.text = result;
            block.color = is_error ? red_color_wrapper : magneta_color_wrapper;
            block.sync()
            this.requestRender();
        }
    }

    public loadMessages(messages: Message[]) {
        this.clear();

        for (const m of messages) {
            if (m.role == "user") {
                this.addText(`> ${m.content}`, cyan_color_wrapper);
            }
            else if (m.role == "assistant") {
                if (m.thinking) {
                    const thinkBlock = this.createCollapsible("Thought", dim_color_wrapper);
                    thinkBlock.text = m.thinking;
                    thinkBlock.sync();
                }

                if (m.content) {
                    const markdownComp = new MarkdownMsgComponent();
                    markdownComp.append(m.content);
                    this.addBlock(markdownComp);
                }

                for (const tc of m.tool_calls ?? []) {
                    const tcBlock = this.createCollapsible(`${tc.name}(${summarizeArgs(tc.arguments)})`, magneta_color_wrapper);
                    tcBlock.detail = JSON.stringify(tc.arguments, null, 2);
                    this.tools_to_component_mapping.set(tc.id, tcBlock);
                    tcBlock.sync();
                }
            }
            else if (m.role == "tool_result") {
                const trBlock = this.tools_to_component_mapping.get(m.tool_call_id);

                if (trBlock) {
                    trBlock.text = m.content
                    trBlock.color = m.is_error ? red_color_wrapper : magneta_color_wrapper;
                    trBlock.sync();
                }
            }
        }

        this.requestRender();
    }

    public endLoop() {
        this.finishThinking();
        this.currentAssistantMarkdownMsgComponent = null;

        this.addText("Done", dim_color_wrapper);
        this.addSpacer(1);
    }

    public clear() {
        this.trajectoryContainer.clear();

        this.currentThinkingBlock = null;
        this.expanded = false;
        this.collapsibles = [];
        this.currentAssistantMarkdownMsgComponent = null;
        this.tools_to_component_mapping = new Map();

        this.requestRender();
    }
}
