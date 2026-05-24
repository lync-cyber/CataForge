#!/usr/bin/env python3
"""Anti-rot guard: document structure hygiene for runtime agent/skill assets.

Scans `.cataforge/agents/**/*.md`, `.cataforge/skills/**/*.md`, and
`.cataforge/rules/**/*.md` for structural anti-patterns that degrade
document quality over time when left unchecked.

Checks:
  1. Non-standard step numbering (e.g. `3a.`, `4b.`) — use sequential
     integers only; sub-steps belong inline or as nested bullets.
  2. Orphaned numbered list gaps (e.g. 1, 2, 4 — missing 3).
  3. Duplicate step numbers within the same section.

Whitelist: append `<!-- allow-doc-structure: <reason> -->` to the
offending line if you have a deliberate reason.
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

SCAN_GLOBS: list[tuple[Path, str]] = [
    (REPO_ROOT / ".cataforge" / "agents", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "rules", "**/*.md"),
]

ALLOW_MARKER = re.compile(r"<!--\s*allow-doc-structure")
CODE_FENCE = re.compile(r"^\s*```")

# Non-standard step numbering: digits followed by a letter then a dot/closing-paren
# e.g. "3a.", "4b)", "2a. **foo**"
NON_STD_STEP = re.compile(r"^(\d+[a-z])[.)]\s")

# Standard numbered list item: "N. " at line start (markdown ordered list)
NUMBERED_STEP = re.compile(r"^(\d+)\.\s")


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


def check_non_standard_numbering(
    lines: list[str],
) -> list[tuple[int, str, str]]:
    """Return (lineno, label, line) for non-standard step numbering."""
    issues: list[tuple[int, str, str]] = []
    in_code_fence = False
    for lineno, line in enumerate(lines, 1):
        if CODE_FENCE.match(line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        if is_whitelisted(line):
            continue
        m = NON_STD_STEP.match(line)
        if m:
            issues.append((
                lineno,
                "non-standard-step",
                f"'{m.group(1)}' — use sequential integers; "
                f"merge sub-steps inline or as nested bullets",
            ))
    return issues


def check_step_gaps(
    lines: list[str],
) -> list[tuple[int, str, str]]:
    """Detect gaps and duplicates in numbered step sequences."""
    issues: list[tuple[int, str, str]] = []
    in_code_fence = False
    seen_in_section: dict[int, int] = {}
    prev_num = 0

    def _flush() -> None:
        nonlocal prev_num
        prev_num = 0
        seen_in_section.clear()

    for lineno, line in enumerate(lines, 1):
        if CODE_FENCE.match(line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue

        # Section header resets sequence tracking
        if re.match(r"^#{1,4}\s", line):
            _flush()
            continue

        if is_whitelisted(line):
            continue

        m = NUMBERED_STEP.match(line)
        if not m:
            # Non-numbered line breaks the sequence context
            if not line.strip() or re.match(r"^\s", line):
                # Blank line or indented continuation — don't break
                continue
            _flush()
            continue

        num = int(m.group(1))

        # Duplicate check
        if num in seen_in_section:
            issues.append((
                lineno,
                "duplicate-step",
                f"step {num} duplicated (first at line {seen_in_section[num]})",
            ))

        # Gap check (only when we have a prior step)
        if prev_num > 0 and num > prev_num + 1:
            issues.append((
                lineno,
                "step-gap",
                f"step {prev_num} → {num} (missing {prev_num + 1})",
            ))

        seen_in_section[num] = lineno
        prev_num = num

    return issues


def main() -> int:
    fails: list[str] = []
    scanned = 0
    for path in iter_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        rel = path.relative_to(REPO_ROOT)

        for lineno, label, msg in check_non_standard_numbering(lines):
            fails.append(f"{rel}:{lineno}: [{label}] {msg}")

        for lineno, label, msg in check_step_gaps(lines):
            fails.append(f"{rel}:{lineno}: [{label}] {msg}")

    if fails:
        print(
            "Anti-rot: document structure issues in runtime agent/skill assets",
            file=sys.stderr,
        )
        for f in fails:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nFix: use sequential integers (1. 2. 3.) for numbered steps. "
            "Merge sub-steps inline or as nested bullets — never use 3a. / 4b. "
            "suffixes. Close numbering gaps by renumbering.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, no document structure issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
