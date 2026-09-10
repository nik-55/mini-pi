import {
    Container,
    Markdown,
    Text,
    TruncatedText,
} from "@earendil-works/pi-tui";

import {
    mdTheme,
    dim_color_wrapper,
    type Colorfn,
} from './theme.js';

class MarkdownMsgComponent extends Container {
    public text: string = "";

    constructor() {
        super();
        this.text = "";
        this.sync();
    }

    append(delta: string) {
        this.text += delta;
        this.sync();
    }

    sync() {
        this.clear(); // sets this.children = []
        if (this.text) {
            this.addChild(new Markdown(this.text, 1, 0, mdTheme));
        }
        super.invalidate();
    }
}

class CollapsibleComponent extends Container {
    public header: string; // single line header, visible when folded or expanded
    public color: Colorfn;
    public detail: string = ""; // argument_json_str for tool call arguments
    public text: string = ""; // tool_result or thinking_tokens
    public expanded: boolean = false;

    constructor(header: string, color: Colorfn) {
        super();
        this.header = header;
        this.color = color;
        this.detail = "";
        this.text = "";
        this.expanded = false;
        this.sync();
    }

    setExpanded(expanded: boolean) {
        this.expanded = expanded;
        this.sync();
    }

    body(): string {
        const parts: string[] = [];
        if (this.detail) parts.push(this.detail);
        if (this.text) parts.push(this.text);
        return parts.join("\n").trim();
    }

    sync() {
        this.clear();
        const arrow = this.expanded ? "▼" : "▶";

        this.addChild(new TruncatedText(this.color(`${arrow} ${this.header}`), 1, 0));

        if (this.expanded) {
            this.addChild(new Text(dim_color_wrapper(this.body()), 1, 0));
        }

        super.invalidate();
    }
}


export {
    MarkdownMsgComponent, CollapsibleComponent
};
