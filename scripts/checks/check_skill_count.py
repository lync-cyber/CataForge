#!/usr/bin/env python3
"""Anti-rot guard: docs claim a skill count that matches the disk.

Fails (exit 1) if any of the watched documents references a count that
disagrees with ``len(.cataforge/skills/<id>/)``.

Why this exists:
    Twice in the v0.1.x series the docs continued to advertise "24 个
    Skill" after self-update was added in v0.1.7 → 25. Static count
    drift is invisible to existing tests (they exercise the runtime,
    not marketing copy), so we explicitly grep the documents that are
    user-facing entry points.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / ".cataforge" / "skills"

# (file, regex) — first capture group is the asserted count. Each pattern
# is checked once; if a doc grew a second mention of "X 个 Skill" the
# regex matches the first and we'll catch the second on the next change.
WATCHED: list[tuple[Path, re.Pattern[str]]] = [
    (REPO_ROOT / "README.md", re.compile(r"(\d+)\s*个\s*Skill")),
    (REPO_ROOT / "docs" / "README.md", re.compile(r"\+\s*(\d+)\s*个\s*Skill")),
    (
        REPO_ROOT / "docs" / "reference" / "agents-and-skills.md",
        re.compile(r"Skill\s*清单（\s*(\d+)\s*个\s*）"),
    ),
]


def actual_count() -> int:
    return sum(1 for p in SKILLS_DIR.iterdir() if p.is_dir())


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print(f"ERROR: {SKILLS_DIR} not found", file=sys.stderr)
        return 1

    expected = actual_count()
    fails: list[str] = []
    for path, pattern in WATCHED:
        if not path.is_file():
            fails.append(f"{path.relative_to(REPO_ROOT)}: file missing")
            continue
        text = path.read_text(encoding="utf-8")
        m = pattern.search(text)
        if m is None:
            fails.append(
                f"{path.relative_to(REPO_ROOT)}: skill-count assertion not found "
                f"(pattern {pattern.pattern!r})"
            )
            continue
        claimed = int(m.group(1))
        if claimed != expected:
            fails.append(
                f"{path.relative_to(REPO_ROOT)}: claims {claimed} skills, "
                f"disk has {expected}"
            )

    if fails:
        print("Anti-rot: skill count drift", file=sys.stderr)
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            f"\nFix: update each doc to reflect the actual count ({expected}).",
            file=sys.stderr,
        )
        return 1

    print(f"OK: skill count {expected} consistent across {len(WATCHED)} docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
