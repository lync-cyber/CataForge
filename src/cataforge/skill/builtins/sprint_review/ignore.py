"""Ignore-pattern + candidate-file enumeration for sprint-review's
unplanned-files (gold-plating) check.

Two layered defenses against monorepo noise:

1. ``DEFAULT_IGNORE_PATTERNS`` — gitignore-style globs covering common
   build / vendor / cache outputs (``node_modules/``, ``dist/``,
   ``*.tsbuildinfo``, ...). Apply even when no .gitignore is present.

2. ``--respect-gitignore`` (default on) — when inside a git work-tree,
   delegate the actual filesystem walk to
   ``git ls-files -co --exclude-standard``, which honours .gitignore,
   submodule boundaries, and CRLF normalisation for free. The default
   patterns above are still applied on top, since some artefacts (e.g.
   *.tsbuildinfo, *.map) aren't always gitignored.

Outside a git repo, or with ``--no-respect-gitignore``, falls back to
``os.walk`` filtered by ``DEFAULT_IGNORE_PATTERNS``.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from collections.abc import Iterable

DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    # VCS / editor metadata
    ".git/",
    ".hg/",
    ".svn/",
    ".idea/",
    ".vscode/",
    # Python build / venv / cache
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    ".venv/",
    "venv/",
    ".tox/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "*.egg-info/",
    "build/",
    "dist/",
    # Node / TS / JS ecosystem
    "node_modules/",
    ".next/",
    ".nuxt/",
    ".turbo/",
    "out/",
    ".cache/",
    "*.tsbuildinfo",
    "*.map",
    # Coverage / lock files
    "coverage/",
    "*.lock",
)


class IgnoreSpec:
    """Minimal gitignore-style pattern matcher.

    Supported syntax (subset of gitwildmatch sufficient for sprint-review):

    * ``name/`` — matches *any* path segment named ``name`` (treats the
      whole subtree as ignored).
    * ``*.ext`` or other bare globs — matched against each path's basename.
    * Globs containing ``/`` — matched against the full posix-normalised
      path with ``fnmatchcase``.

    Lines starting with ``#`` and blank lines are skipped.
    """

    def __init__(self, patterns: Iterable[str]) -> None:
        self._dir_segments: set[str] = set()
        self._basename_globs: list[str] = []
        self._path_globs: list[str] = []
        for raw in patterns:
            pat = raw.strip()
            if not pat or pat.startswith("#"):
                continue
            if pat.endswith("/"):
                self._dir_segments.add(pat.rstrip("/"))
                continue
            if "/" in pat:
                self._path_globs.append(pat.lstrip("/"))
            else:
                self._basename_globs.append(pat)

    def match(self, path: str) -> bool:
        norm = path.replace("\\", "/")
        while norm.startswith("./"):
            norm = norm[2:]
        parts = norm.split("/")
        for seg in parts[:-1]:
            if seg in self._dir_segments:
                return True
        # also match if the file itself is named like a "dir/" pattern's stem
        # — e.g. someone passes "build" (no trailing /) as basename.
        name = parts[-1]
        if any(fnmatch.fnmatchcase(name, g) for g in self._basename_globs):
            return True
        return any(fnmatch.fnmatchcase(norm, g) for g in self._path_globs)


def load_ignore_file(path: str) -> list[str]:
    """Read patterns from a gitignore-style file. Missing file → empty list."""
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            return [line.rstrip("\n") for line in fh]
    except OSError:
        return []


def build_ignore_spec(
    *,
    use_defaults: bool,
    extra_patterns: Iterable[str] = (),
    extra_files: Iterable[str] = (),
) -> IgnoreSpec:
    patterns: list[str] = []
    if use_defaults:
        patterns.extend(DEFAULT_IGNORE_PATTERNS)
    for f in extra_files:
        patterns.extend(load_ignore_file(f))
    patterns.extend(extra_patterns)
    return IgnoreSpec(patterns)


def is_git_repo(cwd: str | None = None) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def git_list_files(src_dirs: list[str], cwd: str | None = None) -> list[str]:
    """Tracked + untracked files (respecting .gitignore) under ``src_dirs``.

    Uses ``git ls-files -co --exclude-standard``: ``-c`` cached (tracked),
    ``-o`` others (untracked but not ignored), ``--exclude-standard``
    applies .gitignore + .git/info/exclude + global excludes.

    Returns posix-normalised paths relative to the git work-tree root
    (which is the same as ``cwd`` when ``cwd`` is the repo root).
    """
    if not src_dirs:
        return []
    cmd = ["git", "ls-files", "-co", "--exclude-standard", "-z", "--", *src_dirs]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=120
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    return [f for f in r.stdout.split("\x00") if f]


def walk_files(src_dirs: list[str]) -> list[str]:
    out: list[str] = []
    for d in src_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            # in-place prune of obviously-noisy dirs to avoid descending
            # into million-file trees before the ignore filter even runs
            dirs[:] = [
                x
                for x in dirs
                if x not in {"node_modules", "__pycache__", ".git"}
            ]
            for f in files:
                out.append(os.path.join(root, f).replace("\\", "/"))
    return out


def list_candidate_files(
    src_dirs: list[str],
    *,
    respect_gitignore: bool,
    ignore_spec: IgnoreSpec,
    cwd: str | None = None,
) -> list[str]:
    """Enumerate files under ``src_dirs``, applying gitignore + ignore spec."""
    if respect_gitignore and is_git_repo(cwd):
        files = git_list_files(src_dirs, cwd=cwd)
    else:
        files = walk_files(src_dirs)
    return [p for p in files if not ignore_spec.match(p)]
