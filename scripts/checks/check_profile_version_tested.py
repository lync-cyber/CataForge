#!/usr/bin/env python3
"""Anti-rot guard: platform profile.yaml staleness.

``version_tested`` records the platform version a profile was last validated
against — a free-form version string (``"3.1"``, ``"2026.04"``), not a date, so
"days since audit" cannot be read from it directly. The honest, self-maintaining
staleness signal is the profile's own git history: the date of the last commit
that touched ``.cataforge/platforms/<id>/profile.yaml``. A profile untouched for
longer than ``MAX_AGE_DAYS`` is flagged so a maintainer re-runs ``platform-audit``
before ``available_models`` / tool names / event names drift into invalid values.

Wired into anti-rot.yml weekly sweep only (a stale profile is a slow-moving
signal, not a per-PR gate). Needs full git history — the sweep checks out with
``fetch-depth: 0``. Exit 1 when any profile is stale so the sweep opens an issue.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORMS_DIR = REPO_ROOT / ".cataforge" / "platforms"
MAX_AGE_DAYS = 180


def _git_commit_date(rel_path: str) -> str | None:
    """ISO-8601 date of the last commit touching *rel_path*, or None if git is
    unavailable / the path has no commit history (untracked)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "-1", "--format=%cI", "--", rel_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    date = out.stdout.strip()
    return date or None


def profile_age_days(commit_iso: str, now: datetime) -> int:
    """Whole days between *commit_iso* and *now* (both timezone-aware)."""
    return (now - datetime.fromisoformat(commit_iso)).days


def find_stale(
    commit_dates: dict[str, str | None], now: datetime, max_age_days: int
) -> list[tuple[str, int]]:
    """``[(platform_id, age_days)]`` for profiles older than *max_age_days*.

    Profiles with no commit date (untracked / no git) are skipped, not flagged.
    """
    stale: list[tuple[str, int]] = []
    for pid, iso in commit_dates.items():
        if iso is None:
            continue
        age = profile_age_days(iso, now)
        if age > max_age_days:
            stale.append((pid, age))
    return stale


def _version_tested(profile_path: Path) -> str:
    try:
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return "?"
    return str(data.get("version_tested", "?"))


def main() -> int:
    if not PLATFORMS_DIR.is_dir():
        print(f"OK: {PLATFORMS_DIR} not present, nothing to scan")
        return 0

    profiles = sorted(p for p in PLATFORMS_DIR.glob("*/profile.yaml"))
    commit_dates: dict[str, str | None] = {}
    for profile in profiles:
        pid = profile.parent.name
        rel = profile.relative_to(REPO_ROOT).as_posix()
        commit_dates[pid] = _git_commit_date(rel)

    now = datetime.now(UTC)
    stale = find_stale(commit_dates, now, MAX_AGE_DAYS)

    untracked = [pid for pid, iso in commit_dates.items() if iso is None]
    if untracked:
        print(f"note: skipped (no git history): {', '.join(sorted(untracked))}")

    if stale:
        print("WARN: stale platform profiles (re-run platform-audit):", file=sys.stderr)
        for pid, age in sorted(stale):
            ver = _version_tested(PLATFORMS_DIR / pid / "profile.yaml")
            print(
                f"  - {pid}: profile.yaml untouched for {age} days "
                f"(> {MAX_AGE_DAYS}); version_tested {ver!r} may be stale",
                file=sys.stderr,
            )
        return 1

    print(f"OK: {len(commit_dates)} platform profiles within {MAX_AGE_DAYS}-day window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
