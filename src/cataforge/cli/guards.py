"""Decorators enforcing CLI invariants.

:func:`require_initialized` is the main export — attach it to any command
that fundamentally cannot work without a ``.cataforge/`` scaffold. The
pre-check fires *before* the command body runs, so users get a friendly
"run cataforge setup first" message instead of a deep FileNotFoundError.

Commands that should NOT use this guard:

* ``setup``    — it creates the scaffold.
* ``doctor``   — it diagnoses missing scaffolds.
* ``--version``/``--help`` — resolved by Click before commands run.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from cataforge.cli.errors import NotInitializedError

F = TypeVar("F", bound=Callable[..., Any])


def require_initialized(func: F) -> F:
    """Ensure ``.cataforge/`` exists before running the wrapped command.

    Raises :class:`NotInitializedError` otherwise, which Click prints as
    ``Error: No .cataforge/ scaffold found ...`` on stderr with exit 1.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        from cataforge.cli.helpers import resolve_project_dir
        from cataforge.core.paths import find_project_root

        # Honour --project-dir if set, else walk up from cwd. This keeps
        # the guard consistent with how subcommand helpers resolve root.
        root = resolve_project_dir() or find_project_root()
        if not (root / ".cataforge").is_dir():
            raise NotInitializedError(root)
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


__all__ = ["require_initialized"]
