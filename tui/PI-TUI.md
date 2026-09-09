# Using `@earendil-works/pi-tui`

Notes on the TUI library behind [`chat.mjs`](./chat.mjs), written while building it.
Grounded in the shipped README (`node_modules/@earendil-works/pi-tui/README.md`, 903
lines), the `.d.ts` files, and pi's own usage in `packages/coding-agent`.

---

## 1. Why there is TypeScript in a Python project

pi-tui is TypeScript, mini-pi is Python. The split:

```
tui/chat.mjs                          coding/rpc.py
   │
   ├─ spawn(.venv/bin/python -m coding.rpc)
   │     stdio: ["pipe", "pipe", "inherit"]
   │
   │   py.stdin  ──── pipe ────►  sys.stdin
   │   {"type":"prompt","text":"hi"}\n      StreamReader → json.loads
   │                                        → CodingSession.prompt(text)
   │
   │   py.stdout ◄─── pipe ────  _out
   │   readline → JSON.parse                json.dumps(event) + "\n"
   │   → switch(e.type) → components
   │
   └─ stderr: "inherit" → straight to the terminal
```

Newline-delimited JSON over two OS pipes. No HTTP, no sockets, no framing library.
Same transport tau uses (`src/tau_coding/rpc.py:150-164`).

`rpc.py` claims the real stdout for the protocol and redirects `sys.stdout` to
stderr, because `coding/session.py:145,155` still call bare `print()` and those
lines would otherwise land in the middle of the JSON stream.

---

## 2. The model

A `TUI` owns a tree of `Component`s. Each component renders itself to lines:

```typescript
interface Component {
  render(width: number): string[];
  handleInput?(data: string): void;
  handleMouse?(event: TuiMouseEvent): TuiMouseEventResult | undefined;
  invalidate(): void;
}
```

The renderer walks the tree, gets lines, diffs against the previous frame, and
writes only what changed — wrapped in CSI 2026 synchronized output
(`\x1b[?2026h` … `\x1b[?2026l`) so the terminal paints atomically. That is the
flicker fix, and it's why streaming at 40 tok/s doesn't tear.

### The one rule that matters

**A component owns its children. Never restructure the top-level tree.**

This is the mistake that cost the most time here. The first version of `chat.mjs`
called `tui.removeChild()` / `tui.addChild()` for every block on every update, and
the transcript rendered twice on screen.

pi does the opposite — see
`packages/coding-agent/src/modes/interactive/components/assistant-message.ts:91`:

```typescript
updateContent(message, isStreaming) {
  this.contentContainer.clear();                      // :96
  this.contentContainer.addChild(new Markdown(...));  // :114
}
```

`AssistantMessageComponent extends Container`. The churn is *inside* the
component; the tree above it never changes. Note it rebuilds the whole `Markdown`
on **every streaming delta** and that is fine — render caching plus differential
output absorb it.

In `chat.mjs` the top-level tree is only ever:

```
[ transcript(Container), loader?, picker?, editor ]
```

Blocks are appended to `transcript`, never to the TUI, and never removed. The
optional slots are transient chrome — a spinner and the session picker — and
`restack()` is the only function permitted to touch them.

---

## 3. Renderers

Both implement the same `TUI` interface; pick one at construction.

| | `TuiMainScreen` | `TuiAltScreen` |
|---|---|---|
| buffer | main, **preserves terminal scrollback** | alternate, app-owned scrolling |
| scrolling | the terminal's | `ScrollView`, wheel + keyboard |
| mouse | **not captured** — terminal owns it | normalized, hit-tested |
| selection / copy | your terminal's | drag-select + OSC 52 clipboard |
| search | your terminal's | `Ctrl+Shift+F` built in |
| `VStack`/`HStack`/`ScrollView` layout | unavailable by design | via `setLayoutRoot()` |
| on stop | leaves output in place | restores main buffer, prints the full document |

`chat.mjs` uses `TuiMainScreen`.

**Consequence: `MouseRegion` and click-to-expand do nothing on main-screen.** The
README is explicit — *"`TuiMainScreen` does not capture mouse input because the
terminal owns its scrollback."* Keyboard only.

`TuiMainScreen` has three render strategies:

1. **First render** — output all lines, don't clear scrollback
2. **Width changed, or change above the viewport** — clear screen, full re-render
3. **Normal update** — cursor to first changed line, clear to end, render changed lines

Strategy 2 is why changing content that has scrolled off is *allowed* but expensive.
If something ever looks doubled on screen, that's the path to suspect.

pi ships both and lets the user switch at runtime
(`modes/interactive/tui-renderer.ts:18-21`), preserving render state across the
swap (`interactive-mode.ts:829`). Worth copying if alt-screen is ever added here.

---

## 4. Components used here

| component | notes |
|---|---|
| `Container` | `children`, `addChild`, `removeChild`, `clear()`, `invalidate()`. The base class for custom blocks. |
| `Box` | Container plus padding and a background function. |
| `Text` | Multi-line, word-wrapped. `setText()`. |
| `TruncatedText` | **Single line**, clips to viewport width. Use for any header that could be long. |
| `Markdown` | `new Markdown(text, padX, padY, theme, defaultStyle?)`. Has `setText()`, and `render(width)` works standalone if you just want a styled string. |
| `Editor` | Multi-line input with history, autocomplete, paste handling. `onSubmit`, `setText()`. Needs an `EditorTheme`. |
| `Loader` | Spinner. `new Loader(tui, spinnerColor, messageColor, message)`, `start()`, `setMessage()`, `stop()`. |
| `CancellableLoader` | `Loader` + Escape handling. `onAbort`, `signal: AbortSignal`, `aborted`. |
| `SelectList` | `new SelectList(items, maxVisible, theme)`. `onSelect`, `onCancel`, `onSelectionChange`, `setFilter()`. Arrow keys, Enter, Escape — needs `tui.setFocus()`. |
| `Spacer` | Blank lines. |
| `SettingsList`, `Image`, `Input`, `MouseRegion`, `VStack`, `HStack`, `ScrollView` | unused here. |

`MarkdownTheme` requires all 14 style functions (`heading`, `link`, `linkUrl`,
`code`, `codeBlock`, `codeBlockBorder`, `quote`, `quoteBorder`, `hr`, `listBullet`,
`bold`, `italic`, `strikethrough`, `underline`); `highlightCode` is optional.
`EditorTheme` needs `borderColor` and a full `SelectListTheme`.

### What is *not* in the box

There is no thinking block, no tool-call component, no collapsible, no chat
widget. Grepping the whole `dist/` for `collaps|expand|fold|disclosure` returns
only unrelated internals. pi-tui is the rendering engine; agent semantics live in
the application. For scale: pi's own interactive mode is **18,631 lines**
(`interactive-mode.ts` alone is 6,620).

---

## 5. Writing a component

```javascript
class CollapsibleComponent extends Container {
  constructor(label, color) {
    super();
    this.label = label;
    this.color = color;
    this.text = "";
    this.expanded = false;
    this.sync();
  }

  sync() {
    this.clear();
    const arrow = this.text ? (this.expanded ? "▼" : "▶") : " ";
    this.addChild(new TruncatedText(this.color(`${arrow} ${this.label}`), 1, 0));
    if (this.text) {
      const lines = this.text.split("\n");
      const shown = this.expanded ? lines : lines.slice(0, 3);
      this.addChild(new Text(dim(shown.join("\n")), 3, 0));
    }
    super.invalidate();   // drop cached render state
  }
}
```

Mutate state → rebuild children → `invalidate()` → `tui.requestRender()`.

### Rules for hand-rolled `render()`

If you implement `render(width)` yourself instead of composing existing
components:

- **Every returned line must be ≤ `width`, or the TUI throws.** Use
  `truncateToWidth(text, width)` or `wrapTextWithAnsi(text, width)`.
- `visibleWidth(s)` measures ignoring ANSI codes. `"\x1b[31mHello\x1b[0m"` is 5.
- **Styles do not survive a line break.** The TUI appends an SGR reset and OSC 8
  reset to every line, so reapply styling per line or use `wrapTextWithAnsi()`,
  which does it for you.
- Cache `{cachedWidth, cachedLines}` and clear it in `invalidate()`. The renderer
  calls `render()` every frame.

---

## 6. Keys

Raw mode means **Ctrl+C does not send SIGINT** — intercept it or the app can't be
quit.

```javascript
tui.addInputListener((data) => {
  if (matchesKey(data, Key.ctrl("c"))) { /* … */ return { consume: true }; }
  if (matchesKey(data, Key.ctrl("o"))) { toggleAll(); return { consume: true }; }
});
```

`addInputListener` returns an unsubscribe function. Return `{ consume: true }` to
stop the key reaching the focused component. `Key.ctrl("c")`, `Key.ctrlShift("p")`,
`Key.alt("left")`, `Key.escape`, `Key.up` — or plain strings, `"ctrl+c"` works too.
Kitty keyboard protocol is supported where the terminal offers it.

Focus is explicit: `tui.setFocus(editor)`, or nothing receives typing.

---

## 7. Walkthrough of `chat.mjs`

544 lines, in seven sections.

| lines | section |
|---|---|
| 1–50 | imports, colours, themes |
| 52–142 | the two custom components |
| 144–176 | agent subprocess, RPC request helpers |
| 178–284 | autocomplete, the tree, the session picker |
| 286–304 | collapse state |
| 306–357 | input, keys, startup |
| 359–544 | event loop and `replay()` |

### 7.1 Colours and themes (17–50)

```javascript
const c = (n) => (s) => `\x1b[${n}m${s}\x1b[0m`;
const dim = c(90), cyan = c(36), magenta = c(35), red = c(31);
```

pi-tui themes are *functions*, `(string) => string`, not colour constants — so any
ANSI helper works and there's no dependency on chalk. `mdTheme` must define all 14
`MarkdownTheme` members; `editorTheme` needs `borderColor` plus a complete
`SelectListTheme` (used by the editor's autocomplete popup, so it can't be `{}`).

### 7.2 `MessageComponent` (60–78)

Streaming assistant text.

```javascript
class MessageComponent extends Container {
  append(delta) { this.text += delta; this.sync(); }
  sync() {
    this.clear();
    if (this.text) this.addChild(new Markdown(this.text, 1, 0, mdTheme));
    super.invalidate();
  }
}
```

Three lines of substance, and it's the whole answer to "how do I render markdown
while streaming". A fresh `Markdown` is built on **every token**, exactly as pi does
in `assistant-message.ts:96`. Half-written `**bold` or an unclosed fence renders as
partial markdown for one frame and corrects itself on the next.

An earlier version streamed into a `Text` node and swapped it for a `Markdown` node
at `turn_end`, to avoid parsing partial markdown. That swap mutated the *top-level*
tree and printed the transcript twice. This version never touches the tree.

### 7.3 `summarizeArgs()` and `CollapsibleComponent` (80–142)

`summarizeArgs()` exists because a `write` tool call carries an entire file in its
arguments. It flattens whitespace and caps each value at 60 chars:

```
write → path: gravity.md, content: # On Gravity Gravity is, in many ways, the mo…
```

`CollapsibleComponent` backs both thinking blocks and tool calls. Its state:

- `label` — header text (`Thinking…`, or `bash(command: pwd)`)
- `detail` — full pretty-printed arguments, shown **only when expanded**
- `text` — the streamed thinking, or the tool result
- `expanded`

`body()` concatenates `detail` + `text`, and `sync()` renders header plus either the
first `PREVIEW_LINES` (3) or everything, with a `… N more lines, ctrl+o to expand`
footer.

The header uses `TruncatedText`, not `Text`. That is deliberate: `Text` word-wraps,
so a long header would silently become fifteen lines. `TruncatedText` is single-line
and clips to viewport width. Both defences are needed — `summarizeArgs()` alone
still produced a header longer than the terminal.

### 7.4 The subprocess and RPC helpers (144–176)

```javascript
const root = new URL("..", import.meta.url).pathname;
const py = spawn(`${root}.venv/bin/python`, ["-m", "coding.rpc"], {
  cwd: root, stdio: ["pipe", "pipe", "inherit"],
});
const send = (msg) => py.stdin.write(JSON.stringify(msg) + "\n");
```

The absolute path matters: `spawn` resolves the command against the *parent's* cwd,
not the `cwd` option, so a relative `../.venv/bin/python` fails with `ENOENT`.
`stdio[2]` is `"inherit"` so Python tracebacks reach the terminal instead of the
JSON stream.

### 7.5 The tree (178–284)

```javascript
const transcript = new Container();   // every block lives in here
const editor = new Editor(tui, editorTheme, { paddingX: 1 });
const loader = new Loader(tui, cyan, dim, "working…");
```

The top-level tree is only ever `[transcript, loader?, picker?, editor]`. Three
helpers:

- `add(component)` — appends to `transcript`. Never to the TUI.
- `restack()` — the *only* function that touches the top level, and only to seat
  the transient chrome (spinner, session picker) between transcript and editor.
- `say(text, color)` — a `Text` plus a `Spacer(1)`.

### 7.6 Collapse (286–304)

`collapsibles` is a flat array of every block ever created; `expanded` is one global
flag. `toggleAll()` flips it and calls `setExpanded()` on each. New blocks inherit
the current flag (`collapsible()` line 293), so creating one while expanded doesn't
produce a mixed view.

Per-block toggling would need `MouseRegion` or a focus/cursor model — and on
`TuiMainScreen` mouse input isn't captured at all (§3), so global-toggle-by-keyboard
is the honest option here.

### 7.7 Input and keys (306–357)

`editor.onSubmit` handles slash commands before the busy check, so `/resume` and
`/session` work mid-turn while a prompt does not (`if (busy) return`).

```javascript
tui.addInputListener((data) => {
  if (matchesKey(data, Key.ctrl("c"))) { … return { consume: true }; }
  if (matchesKey(data, Key.ctrl("o"))) { toggleAll(); return { consume: true }; }
});
```

Ctrl+C is context-sensitive, checked in order: close the session picker if open,
else cancel the turn if busy, else quit. It has to be intercepted here — raw mode
means no SIGINT. Startup order is `addChild` → `addChild` → `setFocus(editor)` →
`start()`; without `setFocus` nothing receives typing.

### 7.8 Autocomplete and the session picker (192–273)

`CombinedAutocompleteProvider` supplies all of it; the Editor renders the dropdown
itself (an internal `SelectList`), so there is no UI code here.

```javascript
editor.setAutocompleteProvider(
  new CombinedAutocompleteProvider(slashCommands, root, findFd()),
);
```

A `SlashCommand` is `{ name, description?, argumentHint?, getArgumentCompletions? }`.
`getArgumentCompletions(prefix)` is what turns `/resume ` into a session picker —
it may be async, so it awaits `listSessions()`, which sends `{type:"list_sessions"}`
and parks a promise until the `sessions` event arrives (2s timeout so the editor
can't hang). The `sessions` handler resolves that promise instead of printing when
a request is pending.

**`@` requires the `fd` binary.** `getFuzzyFileSuggestions()` returns `[]`
immediately when `fdPath` is null (`autocomplete.js:586`) and it defaults to null —
there is no fallback for `@`. `findFd()` looks for `fd` or `fdfind` on PATH, so it
switches on by itself once installed.

Proven by substituting a three-line shell script for the binary — same provider,
same query, only `fdPath` differs:

```
fdPath = null         → null
fdPath = /tmp/fakefd  → cli.py | rpc.py | tools.py
```

Everything else works without `fd`, through a different code path
(`extractPathPrefix` → `getBaseDirSuggestions`):

| input | completes |
|---|---|
| `/` | slash commands with descriptions |
| `/resume ` | session ids, `updated_at` as description |
| `./`, `../`, `~/` | directory listing |
| `agent/se` + Tab | `session/` |
| `@cod` | **nothing without `fd`** |

**Unverified:** `CombinedAutocompleteProvider` never sets `triggerCharacters`, and
the Editor does `provider.triggerCharacters ?? []` (`editor.js:298`), which builds a
regex matching nothing. So the inline dropdown may only appear on **Tab**, not while
typing. Setting `provider.triggerCharacters = ["/", "@"]` before
`setAutocompleteProvider()` is the likely fix if you want as-you-type popups.

### The session picker

`/resume` with **no argument** doesn't print a list to copy from — it opens a real
`SelectList` above the editor:

```
→ 20260910_012156_0bb1            09-10 01:23
  20260909_235734_95c0            09-09 23:57
  20260909_230700_4ba0            09-09 23:07
```

Arrow keys navigate, Enter fires `onSelect` → `{type:"resume", id}`, Escape or
Ctrl+C fires `onCancel`. `SelectList` implements `handleInput()`, so it needs
`tui.setFocus(picker)` to receive keys, and focus returns to the editor on close.

`wantPicker` distinguishes the three consumers of the same `sessions` event: the
picker, `/resume ` autocomplete (resolves `pendingSessions`), and the plain printed
fallback.

### 7.9 Event loop (414–538)

| RPC event | what happens |
|---|---|
| `ready` | banner |
| `session` | `replay()` if there are messages, else clear for a new session |
| `sessions` | 15 most recent, for `/resume` |
| `notice` | dim `Text` |
| `ThinkingDeltaEvent` | append into a `Thinking…` collapsible; relabelled `Thought` when text starts |
| `TextDeltaEvent` | append into `MessageComponent`; closes any open thinking block |
| `ToolExecutionStartEvent` | new collapsible, args in `detail`, registered in `tools` by `tool_call_id` |
| `ToolExecutionEndEvent` | result into `block.text`, header gains `⎿ N lines`, red if `is_error` |
| `AssistantErrorEvent` | red `Text` |
| `turn_end` | close blocks, `busy = false`, stop loader |

`message` and `thinking` are the currently-open blocks; both are nulled at
`ToolExecutionStartEvent` and `turn_end` so the next delta starts a fresh block.
`tools` maps `tool_call_id` → block, which is what lets a result land in the same
collapsible its call created.

### 7.10 `replay()` (368–412)

Rebuilds the transcript from a resumed session's messages. It clears `transcript`,
`collapsibles` and `tools`, then walks the list — `user` → `say()`, `assistant` →
thinking block + `MessageComponent` + one collapsible per tool call, `tool_result` →
looked up by `tool_call_id` and dropped into the matching block.

That last step is why collapse works on resumed history exactly as on live output.

### 7.11 Known rough edges

- **Enter mid-turn is dropped** (line 327). Needs `steer()`/`follow_up()` on the
  harness before it can do anything better.
- **`tools` isn't cleared on `/clear`** — only in `replay()`. Harmless (ids are
  unique) but untidy.
- **`block.label +=` in `ToolExecutionEndEvent`** appends `⎿ N lines`, so a repeated
  end event for the same id would append twice.
- **`transcript.clear()` on resume** shrinks the document, which triggers
  `TuiMainScreen`'s "change above viewport" full re-render. Correct, but it's the
  same code path that produced the original duplicate bug.

### Traps hit while building this

- **Tool arguments can be enormous.** A `write` call carries the entire file. The
  header needs both an arg summariser *and* `TruncatedText`; truncating the result
  alone is not enough.
- **Don't restructure the top-level tree** (§2). This produced a duplicated
  transcript.
- **Markdown mid-stream is fine.** Rebuilding on every delta works; there is no
  need to stream plain text and swap to `Markdown` at the end.
- **Python's stray `print()`** corrupts the protocol. Fixed by redirection in
  `rpc.py`, but the real fix is making `session.py` emit events.

---

## 8. Reference

- Shipped README: `node_modules/@earendil-works/pi-tui/README.md`
- Types: `node_modules/@earendil-works/pi-tui/dist/*.d.ts`
- Real-world usage: pi's `packages/coding-agent/src/modes/interactive/`, especially
  `components/assistant-message.ts` (202 lines) and `components/tool-execution.ts`
  (421 lines)
