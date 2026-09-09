import { spawn, spawnSync } from "node:child_process";
import readline from "node:readline";
import {
  CombinedAutocompleteProvider,
  Container,
  Editor,
  Key,
  Loader,
  Markdown,
  matchesKey,
  ProcessTerminal,
  SelectList,
  Spacer,
  Text,
  TruncatedText,
  TuiMainScreen,
} from "@earendil-works/pi-tui";

const c = (n) => (s) => `\x1b[${n}m${s}\x1b[0m`;
const dim = c(90);
const cyan = c(36);
const magenta = c(35);
const red = c(31);

const PREVIEW_LINES = 3;

const selectList = {
  selectedPrefix: cyan,
  selectedText: cyan,
  description: dim,
  scrollInfo: dim,
  noMatch: dim,
};
const editorTheme = { borderColor: dim, selectList };
const mdTheme = {
  heading: c(1),
  link: cyan,
  linkUrl: dim,
  code: c(32),
  codeBlock: c(32),
  codeBlockBorder: dim,
  quote: dim,
  quoteBorder: dim,
  hr: dim,
  listBullet: cyan,
  bold: c(1),
  italic: c(3),
  strikethrough: c(9),
  underline: c(4),
};

// --- components -------------------------------------------------------------
//
// Following pi's coding-agent: every block is a Container that owns its own
// children. Mutation happens inside via clear() + rebuild, never by adding or
// removing on the top-level tree. See
// packages/coding-agent/src/modes/interactive/components/assistant-message.ts:96

/** Streaming assistant text. Markdown is rebuilt on every delta, like pi. */
class MessageComponent extends Container {
  constructor() {
    super();
    this.text = "";
    this.sync();
  }

  append(delta) {
    this.text += delta;
    this.sync();
  }

  sync() {
    this.clear();
    if (this.text) this.addChild(new Markdown(this.text, 1, 0, mdTheme));
    super.invalidate();
  }
}

/** One-line summary of tool arguments. `write` puts a whole file in there. */
function summarizeArgs(args) {
  return Object.entries(args)
    .map(([key, value]) => {
      let text = typeof value === "string" ? value : JSON.stringify(value);
      text = text.replace(/\s+/g, " ").trim();
      if (text.length > 60) text = `${text.slice(0, 60)}…`;
      return `${key}: ${text}`;
    })
    .join(", ");
}

/** A collapsible block: thinking, or a tool call with its result. */
class CollapsibleComponent extends Container {
  constructor(label, color) {
    super();
    this.label = label;
    this.color = color;
    this.detail = "";
    this.text = "";
    this.expanded = false;
    this.sync();
  }

  setExpanded(expanded) {
    this.expanded = expanded;
    this.sync();
  }

  body() {
    const parts = [];
    if (this.expanded && this.detail) parts.push(this.detail);
    if (this.text) parts.push(this.text);
    return parts.join("\n").trimEnd();
  }

  sync() {
    this.clear();

    const body = this.body();
    const arrow = body ? (this.expanded ? "▼" : "▶") : " ";

    // TruncatedText clips the header to the viewport width, so a tool call
    // carrying an entire file in its arguments stays one line.
    this.addChild(
      new TruncatedText(this.color(`${arrow} ${this.label}`), 1, 0),
    );

    if (body) {
      const lines = body.split("\n");
      const shown = this.expanded ? lines : lines.slice(0, PREVIEW_LINES);
      this.addChild(new Text(dim(shown.join("\n")), 3, 0));

      const hidden = lines.length - shown.length;
      if (hidden > 0) {
        this.addChild(
          new Text(dim(`  … ${hidden} more lines, ctrl+o to expand`), 3, 0),
        );
      }
    }

    super.invalidate();
  }
}

// --- agent subprocess -------------------------------------------------------

const root = new URL("..", import.meta.url).pathname;

const py = spawn(`${root}.venv/bin/python`, ["-m", "coding.headless"], {
  cwd: root,
  stdio: ["pipe", "pipe", "inherit"],
});

const send = (msg) => py.stdin.write(JSON.stringify(msg) + "\n");

// The session list lives in Python, but getArgumentCompletions() is async, so
// the request is wrapped in a promise that the "sessions" event resolves.
let pendingSessions = null;

function listSessions() {
  if (pendingSessions) return pendingSessions.promise;

  const request = {};
  request.promise = new Promise((resolve) => {
    request.resolve = resolve;
    // Don't leave the editor waiting forever if the agent never answers.
    setTimeout(() => resolveSessions([]), 2000);
  });
  pendingSessions = request;
  send({ type: "list_sessions" });
  return request.promise;
}

function resolveSessions(rows) {
  pendingSessions?.resolve(rows);
  pendingSessions = null;
}

// --- ui ---------------------------------------------------------------------

const tui = new TuiMainScreen(new ProcessTerminal());

// One stable Container holds the whole transcript. Blocks are appended to it,
// never to the TUI itself, so the top-level tree is only ever [transcript,
// loader?, editor].
const transcript = new Container();
const editor = new Editor(tui, editorTheme, { paddingX: 1 });
const loader = new Loader(tui, cyan, dim, "working…");

// `/` lists these; `@` and Tab complete file paths. The Editor renders the
// dropdown itself. Third ctor arg is an optional path to `fd`; without it the
// provider falls back to its own directory walking.
const slashCommands = [
  {
    name: "resume",
    description: "Switch to a saved session",
    argumentHint: "<session-id>",
    async getArgumentCompletions(prefix) {
      const rows = await listSessions();
      return rows
        .filter((r) => r.id.includes(prefix))
        .slice(0, 20)
        .map((r) => ({
          value: r.id,
          label: r.id,
          description: r.updated_at.slice(5, 16).replace("T", " "),
        }));
    },
  },
  { name: "clear", description: "Start a new session" },
  { name: "session", description: "Show the active session id" },
  { name: "exit", description: "Quit" },
];

// `@` completion goes through getFuzzyFileSuggestions(), which returns nothing
// unless it has an `fd` binary (autocomplete.js:586). `./`, `../`, `~/` and Tab
// completion work regardless.
function findFd() {
  for (const name of ["fd", "fdfind"]) {
    const found = spawnSync("which", [name], { encoding: "utf8" });
    if (found.status === 0) return found.stdout.trim();
  }
  return null;
}

editor.setAutocompleteProvider(
  new CombinedAutocompleteProvider(slashCommands, root, findFd()),
);

let busy = false;
let picker = null;

// The only function allowed to touch the top level. Order is
// [transcript, loader?, picker?, editor].
function restack() {
  tui.removeChild(loader);
  if (picker) tui.removeChild(picker);
  tui.removeChild(editor);
  if (busy) tui.addChild(loader);
  if (picker) tui.addChild(picker);
  tui.addChild(editor);
  tui.requestRender();
}

/** Arrow-key session picker. SelectList handles nav, Enter and Escape itself. */
function openSessionPicker(rows) {
  closeSessionPicker();

  const items = rows.slice(0, 50).map((r) => ({
    value: r.id,
    label: r.id,
    description: r.updated_at.slice(5, 16).replace("T", " "),
  }));

  if (!items.length) return say("No saved sessions", dim);

  picker = new SelectList(items, 10, selectList);
  picker.onSelect = (item) => {
    closeSessionPicker();
    send({ type: "resume", id: item.value });
  };
  picker.onCancel = () => closeSessionPicker();

  restack();
  tui.setFocus(picker);
}

function closeSessionPicker() {
  if (picker === null) return;
  tui.removeChild(picker);
  picker = null;
  restack();
  tui.setFocus(editor);
}

function add(component) {
  transcript.addChild(component);
  tui.requestRender();
  return component;
}

function say(text, color) {
  add(new Text(color(text), 1, 0));
  add(new Spacer(1));
}

// --- collapse ---------------------------------------------------------------

const collapsibles = [];
let expanded = false;

function collapsible(label, color) {
  const block = new CollapsibleComponent(label, color);
  block.setExpanded(expanded);
  collapsibles.push(block);
  add(block);
  add(new Spacer(1));
  return block;
}

function toggleAll() {
  expanded = !expanded;
  for (const block of collapsibles) block.setExpanded(expanded);
  tui.requestRender();
}

// --- input ------------------------------------------------------------------

editor.onSubmit = (text) => {
  text = text.trim();
  if (!text) return;
  editor.setText("");

  if (text === "/exit") {
    py.kill();
    tui.stop();
    process.exit(0);
  }
  if (text === "/clear") return send({ type: "new_session" });
  if (text === "/session") return say(`Active session: ${sessionId}`, dim);
  if (text.startsWith("/resume")) {
    const id = text.slice("/resume".length).trim();
    if (id) return send({ type: "resume", id });
    wantPicker = true;
    return send({ type: "list_sessions" });
  }

  if (busy) return;

  say(`user> ${text}`, cyan);
  busy = true;
  loader.setMessage("working…");
  loader.start();
  restack();
  send({ type: "prompt", text });
};

tui.addInputListener((data) => {
  if (matchesKey(data, Key.ctrl("c"))) {
    if (picker) closeSessionPicker();
    else if (busy) send({ type: "cancel" });
    else {
      py.kill();
      tui.stop();
      process.exit(0);
    }
    return { consume: true };
  }
  if (matchesKey(data, Key.ctrl("o"))) {
    toggleAll();
    return { consume: true };
  }
});

tui.addChild(transcript);
tui.addChild(editor);
tui.setFocus(editor);
tui.start();

// --- events -----------------------------------------------------------------

let message = null;
let thinking = null;
let sessionId = "";
let wantPicker = false;
const tools = new Map();

/** Rebuild the transcript from a resumed session's message list. */
function replay(messages) {
  transcript.clear();
  collapsibles.length = 0;
  tools.clear();
  message = thinking = null;

  for (const m of messages) {
    if (m.role === "user") {
      say(`user> ${m.content}`, cyan);
      continue;
    }
    if (m.role === "assistant") {
      if (m.thinking) {
        const block = collapsible("Thought", dim);
        block.text = m.thinking;
        block.sync();
      }
      if (m.content) {
        const block = new MessageComponent();
        block.append(m.content);
        add(block);
        add(new Spacer(1));
      }
      for (const tc of m.tool_calls ?? []) {
        const block = collapsible(
          `${tc.name}(${summarizeArgs(tc.arguments)})`,
          magenta,
        );
        block.detail = JSON.stringify(tc.arguments, null, 2);
        tools.set(tc.id, block);
        block.sync();
      }
      continue;
    }
    if (m.role === "tool_result") {
      const block = tools.get(m.tool_call_id);
      if (block) {
        block.text = m.content;
        block.sync();
      }
    }
  }

  tui.requestRender();
}

readline.createInterface({ input: py.stdout }).on("line", (line) => {
  let e;
  try {
    e = JSON.parse(line);
  } catch {
    return;
  }

  switch (e.type) {
    case "ready":
      say(
        `mini-pi · ${e.model}   ctrl+o expand · ctrl+c stop · /resume /clear /session /exit`,
        dim,
      );
      break;

    case "session":
      sessionId = e.session_id;
      if (e.messages.length) {
        replay(e.messages);
        say(`Resumed ${sessionId} · ${e.messages.length} messages`, dim);
      } else if (busy === false && transcript.children.length) {
        transcript.clear();
        collapsibles.length = 0;
        say(`New session ${sessionId}`, dim);
      }
      break;

    case "sessions":
      // `/resume` with no argument opens the picker.
      if (wantPicker) {
        wantPicker = false;
        openSessionPicker(e.rows);
        break;
      }
      // A pending request came from `/resume ` autocomplete, which renders its
      // own dropdown — resolve it instead of printing the list.
      if (pendingSessions) {
        resolveSessions(e.rows);
        break;
      }
      say(
        ["Sessions:"]
          .concat(
            e.rows
              .slice(0, 15)
              .map((r) => `  ${r.updated_at.slice(5, 16).replace("T", " ")}  ${r.id}`),
          )
          .concat("Use /resume <id> to switch")
          .join("\n"),
        dim,
      );
      break;

    case "notice":
      say(e.text, dim);
      break;

    case "ThinkingDeltaEvent":
      if (thinking === null) thinking = collapsible("Thinking…", dim);
      thinking.text += e.delta;
      thinking.sync();
      loader.setMessage("thinking…");
      tui.requestRender();
      break;

    case "TextDeltaEvent":
      if (thinking !== null) {
        thinking.label = "Thought";
        thinking.sync();
        thinking = null;
      }
      if (message === null) {
        message = new MessageComponent();
        add(message);
        add(new Spacer(1));
      }
      message.append(e.delta);
      tui.requestRender();
      break;

    case "ToolExecutionStartEvent": {
      message = null;
      thinking = null;
      const block = collapsible(
        `${e.tool_name}(${summarizeArgs(e.arguments)})`,
        magenta,
      );
      block.detail = JSON.stringify(e.arguments, null, 2);
      block.sync();
      tools.set(e.tool_call_id, block);
      loader.setMessage(`${e.tool_name}…`);
      tui.requestRender();
      break;
    }

    case "ToolExecutionEndEvent": {
      const block = tools.get(e.tool_call_id) ?? collapsible(e.tool_name, magenta);
      const lines = e.result.trim().split("\n").length;
      block.text = e.result;
      block.label += `  ⎿ ${lines} line${lines === 1 ? "" : "s"}`;
      block.color = e.is_error ? red : magenta;
      block.sync();
      loader.setMessage("working…");
      tui.requestRender();
      break;
    }

    case "AssistantErrorEvent":
      message = null;
      say(`✗ ${e.error}`, red);
      break;

    case "loop_end":
      if (thinking !== null) {
        thinking.label = "Thought";
        thinking.sync();
        thinking = null;
      }
      message = null;
      busy = false;
      loader.stop();
      restack();
      break;
  }
});

py.on("exit", () => {
  tui.stop();
  process.exit(0);
});
