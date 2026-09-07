# Mini pi

A minimal coding agent in python.

For the past month I have been exploring how to create an agent from scratch without frameworks, and I have also been digging into how to do evaluations. You can see the experiment artifacts here: https://gitlab.com/nik-55/llm-systems

Based on what I learned there, I want to build a harness that works and stays small. The goal is to keep it readable. Currently it follows the [tau architecture](https://github.com/huggingface/tau)

The current state:
- No AI slop, and around 1700 lines of code
- Streaming responses
- 4 tools (read, write, bash, edit)
- Sandboxing using bwrap on Linux
- Interruption handling
- Session persistence
- A few basic commands (/clear, /session, /resume, /exit)
- REPL only for now
