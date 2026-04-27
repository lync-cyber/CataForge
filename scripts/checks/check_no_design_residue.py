#!/usr/bin/env python3
"""Anti-rot guard: no design-phase residue in runtime agent/skill assets.

`.cataforge/agents/**/AGENT.md` and `.cataforge/skills/**/SKILL.md` are
loaded into the LLM context at runtime. Comments like `<!-- 变更原因：... -->`
or `<!-- diagnostic #N -->` are useful in user docs (`docs/**`) where humans
review changes, but in runtime assets they bloat context and degrade
workflow performance.

This guard blocks the regression. It scans agent / skill markdown for
known design-phase comment markers and fails CI if any are found.

Whitelist: append `<!-- allow-design-residue: <reason> -->` to the
offending line if you have a deliberate reason (e.g. a template placeholder
that gets replaced at deploy time).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_GLOBS: list[tuple[Path, str]] = [
    (REPO_ROOT / ".cataforge" / "agents", "**/AGENT.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/SKILL.md"),
    (REPO_ROOT / ".cataforge" / "agents", "**/*PROTOCOLS*.md"),
    (REPO_ROOT / ".cataforge" / "rules", "**/*.md"),
]

# Markers that almost always indicate design-phase residue carried over
# into runtime assets. Tight by design — if you need to add another
# pattern, write a test case first.
FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    ("变更原因", re.compile(r"<!--\s*变更原因[：:]")),
    ("diagnostic-id", re.compile(r"<!--\s*diagnostic\s*#\d+", re.IGNORECASE)),
    ("TODO-marker", re.compile(r"<!--\s*TODO\s*[:：]")),
    ("FIXME-marker", re.compile(r"<!--\s*FIXME\s*[:：]")),
    ("prompt-version", re.compile(r"<!--\s*prompt-version", re.IGNORECASE)),
    ("last-regenerated", re.compile(r"<!--\s*last-regenerated", re.IGNORECASE)),
]

ALLOW_MARKER = re.compile(r"<!--\s*allow-design-residue")


def is_whitelisted(line: str) -> bool:
    return bool(ALLOW_MARKER.search(line))


def iter_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root, pattern in SCAN_GLOBS:
        if not root.exists():
            continue
        for p in root.glob(pattern):
            if p.is_file() and p not in seen:
                seen.add(p)
                files.append(p)
    return files


def main() -> int:
    fails: list[str] = []
    scanned = 0
    for path in iter_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if is_whitelisted(line):
                continue
            for label, pattern in FORBIDDEN:
                if pattern.search(line):
                    rel = path.relative_to(REPO_ROOT)
                    fails.append(f"{rel}:{lineno}: [{label}] {line.strip()}")

    if fails:
        print(
            "Anti-rot: design-phase residue in runtime agent/skill assets",
            file=sys.stderr,
        )
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: these comments are loaded into LLM context at runtime "
            "and bloat the workflow. Move design rationale to PR description "
            "or commit message; remove the comment from the runtime asset.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, no design-phase residue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
