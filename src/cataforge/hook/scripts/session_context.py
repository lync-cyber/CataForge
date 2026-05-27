"""SessionStart Hook: Log session_start and trigger auto-deploy."""

import sys

from cataforge.hook.base import hook_main, read_hook_input
from cataforge.utils.run_subprocess import run as run_proc


def _auto_deploy() -> None:
    """Run cataforge deploy on session start."""
    try:
        result = run_proc(
            [sys.executable, "-m", "cataforge", "deploy"],
            timeout=15,
        )
        if result.returncode != 0:
            print(
                f"warn: auto-deploy skipped (exit {result.returncode}): "
                f"{(result.stderr or result.stdout).strip()}",
                file=sys.stderr,
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
