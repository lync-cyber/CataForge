#!/usr/bin/env python3
"""Anti-rot guard: the version-migration reference rolls with releases.

``.cataforge/skills/framework-update/references/version-migration.md``
is the only migration signal downstream projects receive (they have no
CataForge CHANGELOG.md, so the ``upgrade check`` BREAKING scan finds
nothing there). Fails (exit 1) if:

  - the newest ``## [X.Y.Z]`` section in CHANGELOG.md has no matching
    ``## [X.Y.Z]`` section in the migration notes (release cut without
    rolling the notes)
  - the migration notes name a version the CHANGELOG does not contain
    (typo or ghost version)

Older CHANGELOG versions may be absent from the notes — the notes keep
a rolling window; CHANGELOG.md is the full archive.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
MIGRATION_NOTES = (
    REPO_ROOT / ".cataforge" / "skills" / "framework-update" / "references" / "version-migration.md"
)

SECTION_RE = re.compile(r"^##\s+\[(\d+\.\d+\.\d+)\]")


def parse_semver(s: str) -> tuple[int, int, int]:
    a, b, c = s.split(".")
    return int(a), int(b), int(c)


def _versions(path: Path) -> list[str]:
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = SECTION_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def main() -> int:
    errors: list[str] = []

    if not CHANGELOG.is_file():
        print(f"ERROR: {CHANGELOG} missing", file=sys.stderr)
        return 1
    if not MIGRATION_NOTES.is_file():
        print(
            f"ERROR: {MIGRATION_NOTES} missing — the version-migration "
            "reference must exist and roll with every release",
            file=sys.stderr,
        )
        return 1

    changelog_versions = set(_versions(CHANGELOG))
    notes_versions = _versions(MIGRATION_NOTES)

    if not changelog_versions:
        print("ERROR: CHANGELOG.md contains no ## [X.Y.Z] sections", file=sys.stderr)
        return 1

    latest = max(changelog_versions, key=parse_semver)
    if latest not in notes_versions:
        errors.append(
            f"newest release {latest} has no '## [{latest}]' section in "
            f"{MIGRATION_NOTES.name} — add its 更新重点/迁移要点 section "
            "(and drop the oldest one past the rolling window)"
        )

    for v in notes_versions:
        if v not in changelog_versions:
            errors.append(
                f"{MIGRATION_NOTES.name} names version {v} which does not "
                "exist in CHANGELOG.md (typo or ghost version)"
            )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
