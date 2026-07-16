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
  4. Indented letter sub-lists (e.g. `a.`, `b)`) — use nested bullets.

Whitelist: append `<!-- allow-doc-structure: <reason> -->` to the
offending line if you have a deliberate reason.
"""

from __future__ import annotations

import re
import sys

from _common import (
    CODE_FENCE,
    REPO_ROOT,
    ensure_utf8,
    is_whitelisted_for,
    iter_asset_files,
    make_escape_hatch,
)

ensure_utf8()

SCAN_GLOBS = [
    (REPO_ROOT / ".cataforge" / "agents", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "skills", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "rules", "**/*.md"),
    (REPO_ROOT / ".cataforge" / "references", "**/*.md"),
    (REPO_ROOT / "docs" / "reference", "**/*.md"),
]

ALLOW = make_escape_hatch("allow-doc-structure")

# Non-standard step numbering at line start: digits + a letter then a
# dot/closing-paren, e.g. "3a.", "4b)", "2a. **foo**".
NON_STD_STEP = re.compile(r"^(\d+[a-z])[.)]\s")

# Same anti-pattern hiding in a heading (`### 3a. …`) or a table cell
# (`| 3a. … |`) — the `^`-anchored NON_STD_STEP misses both, so detect them
# explicitly. A hierarchical dotted heading (`### 3.1 …`) has a digit, not a
# letter, after the number and is intentionally not matched.
NON_STD_HEADING = re.compile(r"^#{1,6}\s+(\d+[a-z])[.)]")
NON_STD_TABLE_CELL = re.compile(r"\|\s*(\d+[a-z])[.)]\s")

# Standard numbered list item: "N. " at line start (markdown ordered list)
NUMBERED_STEP = re.compile(r"^(\d+)\.\s")

# Indented letter sub-list: "  a. ", "  b) " — use nested bullets instead
LETTER_SUBLIST = re.compile(r"^\s+([a-z])[.)]\s")


def is_whitelisted(line: str) -> bool:
    return is_whitelisted_for(line, ALLOW)


def iter_files() -> list:
    return list(iter_asset_files(SCAN_GLOBS))


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
        m = NON_STD_STEP.match(line) or NON_STD_HEADING.match(line)
        if m:
            issues.append(
                (
                    lineno,
                    "non-standard-step",
                    f"'{m.group(1)}' — use sequential integers; "
                    f"merge sub-steps inline or as nested bullets",
                )
            )
            continue
        cell = NON_STD_TABLE_CELL.search(line)
        if cell:
            issues.append(
                (
                    lineno,
                    "non-standard-step-in-table",
                    f"'{cell.group(1)}' in a table cell — use sequential "
                    f"integers; never letter-suffixed sub-steps",
                )
            )
    return issues


def check_letter_sublist(
    lines: list[str],
) -> list[tuple[int, str, str]]:
    """Return (lineno, label, line) for indented letter sub-lists (a. b. c.)."""
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
        m = LETTER_SUBLIST.match(line)
        if m:
            issues.append(
                (
                    lineno,
                    "letter-sublist",
                    f"'{m.group(1)}.' — use nested bullets (-) for sub-steps, "
                    f"not letter enumeration",
                )
            )
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
            issues.append(
                (
                    lineno,
                    "duplicate-step",
                    f"step {num} duplicated (first at line {seen_in_section[num]})",
                )
            )

        # Gap check (only when we have a prior step)
        if prev_num > 0 and num > prev_num + 1:
            issues.append(
                (
                    lineno,
                    "step-gap",
                    f"step {prev_num} → {num} (missing {prev_num + 1})",
                )
            )

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

        for lineno, label, msg in check_letter_sublist(lines):
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
            "Merge sub-steps inline or as nested bullets (-) — never use 3a. / "
            "4b. suffixes or a. / b. letter sub-lists. Close numbering gaps by "
            "renumbering.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {scanned} files, no document structure issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
