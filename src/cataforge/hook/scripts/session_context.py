"""SessionStart Hook: Log session_start and trigger auto-deploy."""

import subprocess
import sys

from cataforge.hook.base import hook_main, read_hook_input


def _auto_deploy() -> None:
    """Run cataforge deploy on session start."""
    try:
        subprocess.run(
            [sys.executable, "-m", "cataforge", "deploy"],
            timeout=15,
            capture_output=True,
            check=True,
        )
    except Exception as e:
        print(f"warn: auto-deploy skipped: {e}", file=sys.stderr)


@hook_main
def main() -> None:
    read_hook_input()
    _auto_deploy()
    sys.exit(0)


if __name__ == "__main__":
    main()
