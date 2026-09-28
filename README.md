# minipi

A lightweight coding agent, heavily inspired by [pi](https://github.com/earendil-works/pi). It is written in Python for better readability.

```text
▄███████▄
█ • ◡ • █
  █   █  
  █   █▄ 
```

## Features

- Streaming responses
- 4 tools: `read`, `write`, `edit`, `bash` with a minimal sandbox
- Project context loading (loads `AGENTS.md` and `.agents/skills`)
- Support for commands (slash commands, e.g. `/rewind`, `/resume`, `/permission`)
- Session persistence to `~/.mini-pi`
- Support for hooks, which are triggered at specific points in the agent lifecycle (e.g. input hook, pre tool call, post tool call)
- Support for extensions (to expand the capabilities of the agent). This includes adding new tools, adding new AI vendors, and adding commands.
- Auto compaction (or `/compact <custom instructions>`) to compact the older messages
- Basic TUI
- Support for steering and follow-ups

A few things:
- Built-in support only for the OpenAI Chat Completions API. Tested only on [fireworks.ai](https://fireworks.ai/models) (with a few models), though more vendors can be added via extensions.
- I tested it only on Ubuntu, though it should work on other OSes.
- The sandbox supports only Linux.

## Setup

- System requirements: Python, uv and Node.js (for the TUI).
- Run `uv tool install mini-pi-agent`. See PyPI [here](https://pypi.org/project/mini-pi-agent/).
- `cd` to the workspace you want to work in and run `minipi`.
- Run `/login fireworks fw_UIO...`. The API key persists in raw form in `~/.mini-pi/auth.json`.
- Run `/help` to learn about more commands.
