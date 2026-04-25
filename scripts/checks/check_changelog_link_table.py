#!/usr/bin/env python3
"""Anti-rot guard: every released version in CHANGELOG has a reference link.

Fails (exit 1) if:
  - any ``## [X.Y.Z]`` section header has no matching ``[X.Y.Z]:`` link
  - any ``[X.Y.Z]:`` link has no matching ``## [X.Y.Z]`` section
    (orphan link — its tag may have moved or been deleted, leading
    readers to a 404)
  - the ``[Unreleased]: ...compare/vX.Y.Z...HEAD`` base does not match
    the highest ``## [X.Y.Z]`` section (i.e. someone added a release
    section but forgot to bump the Unreleased base, leaving the diff
    range pointing at an obsolete tag)

This is exactly the failure mode the v0.1.13 audit found: the
``[Unreleased]`` base sat on v0.1.9 while three real releases (0.1.10
through 0.1.12) had no link entries.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

SECTION_RE = re.compile(r"^##\s+\[(\d+\.\d+\.\d+)\]")
LINK_RE = re.compile(r"^\[(\d+\.\d+\.\d+)\]:")
UNRELEASED_RE = re.compile(
    r"^\[Unreleased\]:\s*https?://[^\s]*compare/v(\d+\.\d+\.\d+)\.\.\.HEAD"
)


def parse_semver(s: str) -> tuple[int, int, int]:
    a, b, c = s.split(".")
    return int(a), int(b), int(c)


def main() -> int:
    if not CHANGELOG.is_file():
        print(f"ERROR: {CHANGELOG} missing", file=sys.stderr)
        return 1

    sections: set[str] = set()
    links: set[str] = set()
    unreleased_base: str | None = None

    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        m = SECTION_RE.match(line)
        if m:
            sections.add(m.group(1))
            continue
        m = LINK_RE.match(line)
        if m:
            links.add(m.group(1))
            continue
        m = UNRELEASED_RE.match(line)
        if m:
            unreleased_base = m.group(1)

    fails: list[str] = []

    missing_links = sorted(sections - links, key=parse_semver)
    if missing_links:
        fails.append(
            "Sections without reference links: "
            + ", ".join(missing_links)
            + " — readers will see plain text instead of a clickable release URL."
        )

    orphan_links = sorted(links - sections, key=parse_semver)
    if orphan_links:
        fails.append(
            "Reference links without sections: "
            + ", ".join(orphan_links)
            + " — link target probably 404 once the corresponding tag is checked."
        )

    if sections:
        latest = max(sections, key=parse_semver)
        if unreleased_base is None:
            fails.append(
                "[Unreleased]: ...compare/vX...HEAD line missing or unparsable."
            )
        elif unreleased_base != latest:
            fails.append(
                f"[Unreleased] compares against v{unreleased_base}, "
                f"but latest released section is [{latest}]. "
                f"Bump the diff base to v{latest}."
            )

    if fails:
        print("Anti-rot: CHANGELOG link table drift", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"OK: CHANGELOG link table consistent "
        f"({len(sections)} sections, {len(links)} links, "
        f"[Unreleased] @ v{unreleased_base})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
