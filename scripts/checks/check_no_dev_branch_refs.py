#!/usr/bin/env python3
"""Anti-rot guard: no resurrected references to the retired `dev` branch.

CataForge dropped the long-lived `dev` branch in v0.1.9 (#56) and finished
the cleanup in v0.1.13. Workflows / templates / dogfood docs must not
reintroduce it — fail (exit 1) if any forbidden phrase appears in
`.github/` or `.cataforge/scripts/dogfood/`.

Whitelisted strings (intentional historical context, not a regression):
    - "原\"长期 dev 分支" or "退役" lines explaining the removal
    - prepare-pr.sh's "形态 C" history note
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRS = [
    REPO_ROOT / ".github",
    REPO_ROOT / ".cataforge" / "scripts" / "dogfood",
]

# Patterns that indicate a regression. Be tight — only the strings that
# would mean "we forgot the dev retirement" rather than any mention of dev.
FORBIDDEN: list[re.Pattern[str]] = [
    re.compile(r"branches:\s*\[\s*main\s*,\s*dev\s*\]"),
    re.compile(r"on\s+(?:dev|the\s+dev)\s+(?:branch|分支)\s+(?:work|工作|run|跑|运行)"),
    re.compile(r"long-lived\s+dev"),
    re.compile(r"git\s+worktree\s+add[^\n]*\bdev\b"),
    re.compile(r"git\s+(push|pull|fetch|checkout)\s+origin\s+dev\b"),
]

# Phrases that are legitimate historical context — exempt the whole line.
WHITELIST_LINE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"已退役|不再有.*?dev|退役.*?dev|历史.*?dev|历史上.*?dev"),
    re.compile(r"形态\s*C"),  # prepare-pr.sh background context
    re.compile(r"#\s*CataForge", re.IGNORECASE),  # comment headers
]


def is_whitelisted(line: str) -> bool:
    return any(p.search(line) for p in WHITELIST_LINE_PATTERNS)


def main() -> int:
    fails: list[str] = []
    scanned = 0

    for root in SCAN_DIRS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in {".pyc", ".png", ".jpg"}:
                continue
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if is_whitelisted(line):
                    continue
                for pattern in FORBIDDEN:
                    if pattern.search(line):
                        rel = path.relative_to(REPO_ROOT)
                        fails.append(f"{rel}:{lineno}: {line.strip()}")

    if fails:
        print("Anti-rot: dev-branch reference resurrected", file=sys.stderr)
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: dev branch retired in #56/v0.1.9. Use feature branches "
            "+ prepare-pr.sh instead. See .cataforge/scripts/dogfood/README.md.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, no forbidden dev-branch references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
