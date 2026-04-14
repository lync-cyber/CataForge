"""SessionStart Hook: Log session_start and trigger auto-deploy.

Design notes:
  - Hook-injected context has low attention weight for the LLM, so env info
    is baked into CLAUDE.md via setup.py --emit-env-block at Bootstrap time.
  - This hook audits session starts and triggers PROJECT-STATE → CLAUDE.md sync.
"""

import contextlib
import subprocess
import sys

from cataforge.hook.base import hook_main, read_hook_input


def _auto_deploy() -> None:
    """Run cataforge deploy on session start."""
    with contextlib.suppress(Exception):
        subprocess.run(
            [sys.executable, "-m", "cataforge", "deploy"],
            timeout=15,
            capture_output=True,
        )


@hook_main
def main() -> None:
    read_hook_input()
    _auto_deploy()
    sys.exit(0)


if __name__ == "__main__":
    main()
