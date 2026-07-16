"""Interpreter resolution for generated hook commands.

Hook commands embed this process's own ``sys.executable``: the Python that
runs ``cataforge deploy`` is the one interpreter guaranteed to import
cataforge under every install method (uv tool / pipx / venv pip), whereas a
bare ``python`` may resolve to an unrelated interpreter — e.g. the Windows
Store shim — that cannot.
"""

from __future__ import annotations

import sys
from pathlib import Path


def interpreter_path() -> str:
    """``sys.executable`` normalized to forward slashes.

    The forward-slash spelling executes under cmd.exe, POSIX shells and
    Windows CreateProcess alike, so one form serves every platform config.
    """
    return Path(sys.executable).as_posix()


def interpreter_command() -> str:
    """Quoted interpreter path for embedding in a shell command string."""
    return f'"{interpreter_path()}"'


def hook_command_template() -> str:
    """Hook command template with a ``{module}`` placeholder.

    The interpreter part is brace-escaped so ``str.format`` only substitutes
    ``{module}`` even when the interpreter path itself contains braces.
    """
    interpreter = interpreter_command().replace("{", "{{").replace("}", "}}")
    return f"{interpreter} -m cataforge.runtime.hook.scripts.{{module}}"
