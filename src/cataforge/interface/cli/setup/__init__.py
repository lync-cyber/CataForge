"""cataforge setup — project initialization.

Command layout (one module each):
- _main: the ``setup`` group itself (invoke_without_command) — the main flow
- _flow: private helpers behind the main flow (scaffold, config apply, dry-run)
- stack: stack-scoped subcommands — env-block, permissions, gitattributes
"""

from __future__ import annotations

from cataforge.interface.cli.setup._main import setup_command as setup_command

from . import stack  # noqa: E402,F401
