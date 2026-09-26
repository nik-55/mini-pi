import os
from pathlib import Path
import shutil
import sys

from coding.main import run


def main():
    node_bin = shutil.which("node")

    env = os.environ
    env["MINI_PI_PYTHON"] = sys.executable
    root_dir = str(Path(__file__).parent.parent)
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{root_dir}:{pythonpath}" if pythonpath else root_dir

    if not node_bin:
        print(
            "[WARNING] 'Node.js (node)' executable not found on PATH\n"
            "Install Node.js from https://nodejs.org/en/download\n"
            "TUI is dependent on it, so REPL based CLI is launching instead\n",
            file=sys.stderr,
        )

        run("cli")
        return

    bundle_path = Path(__file__).parent / "tui_dist" / "mini-pi-tui.mjs"

    if not bundle_path.exists():
        print(f"Error: TUI not found at {bundle_path}", file=sys.stderr)
        sys.exit(1)

    args = [node_bin, str(bundle_path)] + sys.argv[1:]

    os.execvpe(node_bin, args, env.copy())


if __name__ == "__main__":
    main()
