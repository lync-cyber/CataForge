"""B4 — bare numeric literals that should reference framework constants."""

from __future__ import annotations

import re
from pathlib import Path

from .._constants import CONSTANT_LITERALS
from .._types import Report


def check_b4_hardcoded_constants(root: Path, report: Report) -> None:
    """B4-α: bare numeric literals that should reference constants."""
    scan_roots = (
        root / ".cataforge" / "agents",
        root / ".cataforge" / "skills",
        root / ".cataforge" / "rules",
    )
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = str(path)
            in_code_block = False
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.lstrip()
                if stripped.startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block:
                    continue
                # Strip backtick-wrapped spans first: those are quoted
                # examples (e.g. "`≤3 问`" appearing in framework-review's
                # own SKILL.md to *describe* the rule), not literal usage.
                line_outside_inline_code = re.sub(r"`[^`]*`", "", line)
                # Markdown table rows define the constant value itself
                # (e.g. ``| MAX_QUESTIONS_PER_BATCH | 3 |``); drop them
                # so the canonical row isn't mis-flagged.
                if stripped.startswith("|"):
                    continue
                for const_name, pattern, hint in CONSTANT_LITERALS:
                    if const_name in line:
                        continue
                    if re.search(pattern, line_outside_inline_code):
                        report.add(
                            "B4_hardcoded_constants",
                            "WARN",
                            f"{rel}:{lineno}",
                            f"裸数值 {hint!r} 未引用常量名 {const_name}",
                        )
