"""File-system and launcher helpers shared by all code-review checks."""

from __future__ import annotations

import fnmatch
import os
import shutil
from collections.abc import Iterable, Iterator
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

# Generated / vendored files that are never hand-authored source: linting a
# minified third-party bundle only yields config-error false positives, and
# feeding it to duplication/complexity probes is noise. Matched by filename
# glob (or relative-path glob) against the walked tree AND rendered into the
# probe ignore list so both exclusion surfaces stay a single source.
EXCLUDE_FILE_GLOBS = frozenset(
    {
        "*.min.js",
        "*.min.mjs",
        "*.min.css",
        "*.bundle.js",
        "*.bundle.mjs",
        "*.map",
        "*-lock.json",
        "*.generated.*",
        "*.d.ts",
    }
)

_PROJECT_IGNORE_REL = ("skills", "code-review", "ignore")


def load_project_ignore(project_root: Path | None) -> frozenset[str]:
    """Extra exclusion globs from ``.cataforge/skills/code-review/ignore``.

    One glob per line, ``#`` comments and blanks skipped. Opt-in per project
    so a downstream repo can exclude its own vendored/generated paths without
    touching the framework defaults."""
    if project_root is None:
        return frozenset()
    ignore_file = project_root / ".cataforge" / Path(*_PROJECT_IGNORE_REL)
    if not ignore_file.is_file():
        return frozenset()
    globs: set[str] = set()
    for raw in ignore_file.read_text(errors="replace").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            globs.add(line)
    return frozenset(globs)


def _excluded_file(path: Path, root: Path, globs: frozenset[str]) -> bool:
    name = path.name
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = name
    return any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(rel, g) for g in globs)


def iter_files(root: Path, exclude_file_globs: Iterable[str] = ()) -> Iterator[Path]:
    """Yield files under *root*, pruning ``EXCLUDE_DIRS`` in place so os.walk
    never descends into them (rglob would walk the whole tree then filter),
    and skipping generated/vendored files (``EXCLUDE_FILE_GLOBS`` plus any
    project ignore globs)."""
    globs = EXCLUDE_FILE_GLOBS | frozenset(exclude_file_globs)
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        base = Path(dirpath)
        for fn in filenames:
            candidate = base / fn
            if _excluded_file(candidate, root, globs):
                continue
            yield candidate


def probe_ignore_globs(extra_file_globs: Iterable[str] = ()) -> str:
    """Comma-joined glob form of the exclusion surfaces for probes that walk
    the target tree themselves (jscpd) — ``iter_files`` pruning never reaches
    them, so without an explicit ignore a workspace package's node_modules
    blows the probe timeout. Rendered from the SAME ``EXCLUDE_DIRS`` /
    ``EXCLUDE_FILE_GLOBS`` (+ project ignore) so the exclusion surfaces cannot
    drift."""
    globs = [f"**/{d}/**" for d in sorted(EXCLUDE_DIRS)]
    for g in sorted(EXCLUDE_FILE_GLOBS | frozenset(extra_file_globs)):
        globs.append(g if "/" in g else f"**/{g}")
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
