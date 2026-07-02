"""File-system and launcher helpers shared by all code-review checks."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    ".svelte-kit",
    "coverage",
    "bin",
    "obj",
}


def iter_files(root: Path) -> Iterator[Path]:
    """Yield files under *root*, pruning ``EXCLUDE_DIRS`` in place so os.walk
    never descends into them (rglob would walk the whole tree then filter)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        base = Path(dirpath)
        for fn in filenames:
            yield base / fn


def probe_ignore_globs() -> str:
    """Comma-joined glob form of ``EXCLUDE_DIRS`` for probes that walk the
    target tree themselves (jscpd) — ``iter_files`` pruning never reaches
    them, so without an explicit ignore a workspace package's node_modules
    blows the probe timeout. Rendered from ``EXCLUDE_DIRS`` so the two
    exclusion surfaces cannot drift."""
    globs = [f"**/{d}/**" for d in sorted(EXCLUDE_DIRS)]
    globs.append("**/*.d.ts")
    return ",".join(globs)


def resolved(argv: list[str]) -> list[str]:
    """Resolve argv[0] to its PATHEXT-aware absolute path.

    Windows ``subprocess`` only appends ``.exe`` to a bare launcher name, so
    ``.cmd`` / ``.bat`` shims (npx, eslint) raise ``FileNotFoundError`` unless
    given their resolved path. A name ``shutil.which`` can't find is returned
    unchanged, preserving the caller's FileNotFoundError "未安装" skip path.
    """
    exe = shutil.which(argv[0])
    return [exe, *argv[1:]] if exe else list(argv)
