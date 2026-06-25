"""Shell-preference doctor check — warn when the bash preference can't resolve.

Advisory only (always returns 0): on Windows the deployed settings seed
``CLAUDE_CODE_USE_POWERSHELL_TOOL=0`` so the Bash tool stays on Git Bash, which
requires Git for Windows. When that preference is in effect but no Git Bash is
resolvable, the Bash tool would be unusable — surface it as a WARN with the
remedy. Non-Windows and PowerShell-allowed setups are skipped.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from cataforge.core.io import read_json

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def _git_bash_resolvable() -> bool:
    """True when a Git Bash executable can be located on this machine."""
    declared = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if declared and Path(declared).is_file():
        return True
    return shutil.which("bash") is not None


def check_shell_preference(cfg: ConfigManager) -> int:
    """Warn on Windows when settings prefer Git Bash but none is resolvable."""
    if sys.platform != "win32":
        click.echo("  not Windows — skipped.")
        return 0

    settings = cfg.paths.root / ".claude" / "settings.json"
    if not settings.is_file():
        click.echo("  no .claude/settings.json — skipped.")
        return 0

    try:
        data = read_json(settings)
    except Exception:
        click.echo("  settings.json unreadable — skipped.")
        return 0

    env = data.get("env", {}) if isinstance(data, dict) else {}
    prefers_bash = isinstance(env, dict) and env.get("CLAUDE_CODE_USE_POWERSHELL_TOOL") == "0"
    if not prefers_bash:
        click.echo("  PowerShell tool not disabled — skipped.")
        return 0

    if _git_bash_resolvable():
        click.echo("  OK — Git Bash resolvable.")
        return 0

    click.echo(
        "  WARN: settings set CLAUDE_CODE_USE_POWERSHELL_TOOL=0 (prefer Git Bash) "
        "but no Git Bash was found — the Bash tool will be unusable."
    )
    click.echo(
        "  remedy: install Git for Windows, or set CLAUDE_CODE_GIT_BASH_PATH to "
        "bash.exe, or remove the env key to fall back to the PowerShell tool."
    )
    return 0
