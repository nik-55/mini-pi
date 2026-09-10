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

import { splitTextbyWidth } from "./formatters.js";

const PREVIEW_LINES = 2;

class MessageComponent extends Container {
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

    // What text to show at current expanded state
    body(): string {
        const parts: string[] = [];
        if (this.expanded && this.detail) parts.push(this.detail);
        if (this.text) parts.push(this.text);
        return parts.join("\n").trim();
    }

    sync() {
        this.clear();
        const body = this.body();
        const arrow = body ? (this.expanded ? "<" : ">") : " ";

        this.addChild(new TruncatedText(this.color(`${arrow} ${this.header}`), 1, 0));

        if (body) {
            const lines_by_width = splitTextbyWidth(body);
            const shown = this.expanded ? lines_by_width : lines_by_width.slice(0, PREVIEW_LINES);

            this.addChild(new Text(dim_color_wrapper(shown.join("\n")), 3, 0));

            const hidden = lines_by_width.length - shown.length;

            if (hidden > 0) {
                this.addChild(
                    new Text(dim_color_wrapper(` ...${hidden} more lines, ctrl+o to expand`), 3, 0)
                );
            }
        }

        super.invalidate();
    }
}


export {
    MessageComponent, CollapsibleComponent
};
