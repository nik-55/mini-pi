import os
from pathlib import Path
import shutil
import sys


def main():
    node_bin = shutil.which("node")

    if not node_bin:
        print(
            "Error: 'node' executable not found on PATH\n"
            "Node.js is required to run the mini-pi",
            file=sys.stderr,
        )

        sys.exit(1)

    bundle_path = Path(__file__).parent / "tui_dist" / "mini-pi-tui.mjs"

    if not bundle_path.exists():
        print(f"Error: TUI not found at {bundle_path}", file=sys.stderr)
        sys.exit(1)

    env = os.environ.copy()
    env["MINI_PI_PYTHON"] = sys.executable

    root_dir = str(Path(__file__).parent.parent)
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{root_dir}:{pythonpath}" if pythonpath else root_dir

    args = [node_bin, str(bundle_path)] + sys.argv[1:]

    os.execvpe(node_bin, args, env)


if __name__ == "__main__":
    main()
