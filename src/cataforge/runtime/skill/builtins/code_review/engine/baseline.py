"""Ratchet baselines + git-diff incremental scope for gating checks.

A baseline maps a stable fingerprint (e.g. ``rel/path.py::func``) to its
recorded metric values. Scan mode refreshes the file; review mode reads
it and gates only diff-touched entries against
``max(fail threshold, baseline value)`` — touched code must not get
worse than its recorded state, untouched legacy never blocks.

Baseline files live under ``<project_root>/.cataforge/baselines/`` and
are tamper-guarded by framework-review B3-γ: a commit changing one must
also change a ``docs/reviews/code/CODE-SCAN-*.md`` report.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from cataforge.utils.run_subprocess import run as run_proc

BASELINES_DIRNAME = "baselines"
GIT_TIMEOUT_SECS = 30

_DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def baseline_path(project_root: Path, name: str) -> Path:
    return project_root / ".cataforge" / BASELINES_DIRNAME / name


def load_baseline(project_root: Path, name: str) -> dict[str, dict[str, int]]:
    """Recorded metrics by fingerprint; empty on missing/corrupt file."""
    path = baseline_path(project_root, name)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    metrics = data.get("metrics") if isinstance(data, dict) else None
    return metrics if isinstance(metrics, dict) else {}


def save_baseline(project_root: Path, name: str, metrics: dict[str, dict[str, int]]) -> Path:
    path = baseline_path(project_root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "metrics": {key: metrics[key] for key in sorted(metrics)},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def _git(root: Path, *args: str) -> str | None:
    try:
        result = run_proc(["git", *args], cwd=root, timeout=GIT_TIMEOUT_SECS)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _parse_unified_zero(diff: str) -> dict[str, list[tuple[int, int]]]:
    ranges: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in diff.splitlines():
        file_match = _DIFF_FILE_RE.match(line)
        if file_match:
            current = file_match.group(1)
            continue
        hunk = _HUNK_RE.match(line)
        if hunk and current and current != "/dev/null":
            start = max(1, int(hunk.group(1)))
            count = int(hunk.group(2)) if hunk.group(2) is not None else 1
            ranges.setdefault(current, []).append((start, start + max(count, 1) - 1))
    return ranges


def changed_line_ranges(root: Path) -> dict[str, list[tuple[int, int]]] | None:
    """New-side changed line ranges per repo-relative posix path.

    Covers the working tree vs HEAD plus untracked files (whole-file
    range). ``None`` = git information unavailable (not a repo, no git,
    no HEAD) — callers treat everything as touched.
    """
    diff = _git(root, "diff", "--unified=0", "--no-color", "HEAD")
    if diff is None:
        return None
    ranges = _parse_unified_zero(diff)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard")
    if untracked:
        for rel in untracked.splitlines():
            rel = rel.strip()
            if rel:
                ranges.setdefault(rel, []).append((1, sys.maxsize))
    return ranges


def overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= end and start <= b for a, b in ranges)
