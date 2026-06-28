#!/usr/bin/env python3
"""Shared helpers for the anti-rot guard scripts.

Single-sources the boilerplate that three near-identical guards
(``check_no_design_residue`` / ``check_no_language_coupling`` /
``check_doc_structure``) previously each re-implemented and drifted on:
the stdio UTF-8 reconfigure, the asset-file walk, fenced-code-block plus
YAML-frontmatter skipping, and the inline escape-hatch marker. Each guard
imports from here so a coverage or exemption fix lands in one place.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def ensure_utf8() -> None:
    """Reconfigure stdout/stderr to UTF-8 so Chinese diagnostics don't crash
    on Windows cp1252 terminals. Idempotent; safe to call more than once."""
    for _name in ("stdout", "stderr"):
        stream = getattr(sys, _name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


CODE_FENCE = re.compile(r"^\s*```")
FRONTMATTER_FENCE = re.compile(r"^---\s*$")


def iter_asset_files(globs: list[tuple[Path, str]]) -> Iterator[Path]:
    """Yield every existing file matched by the ``(root, glob)`` pairs,
    de-duplicated and in a stable sorted order. Roots that don't exist are
    skipped so a guard can list optional trees without a guard clause."""
    seen: set[Path] = set()
    for root, pattern in globs:
        if not root.exists():
            continue
        for p in sorted(root.glob(pattern)):
            if p.is_file() and p not in seen:
                seen.add(p)
                yield p


def make_escape_hatch(marker: str) -> re.Pattern[str]:
    """Compile a case-insensitive ``<!-- marker ... -->`` matcher. IGNORECASE
    so ``Allow-Design-Residue`` is honoured exactly like the lowercase form."""
    return re.compile(rf"<!--\s*{re.escape(marker)}", re.IGNORECASE)


def is_whitelisted_for(line: str, escape_hatch: re.Pattern[str]) -> bool:
    """True when the line carries the guard's inline escape-hatch comment."""
    return bool(escape_hatch.search(line))


def iter_scannable_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(lineno, line)`` for lines a content guard should inspect:
    everything outside fenced code blocks and a leading YAML frontmatter
    block. Fences hold literal examples (regex strings, sample YAML/shell);
    frontmatter holds machine metadata and sanctioned ``version:`` fields.
    Line numbers are 1-based and count skipped lines so they stay accurate."""
    in_fence = False
    in_frontmatter = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if lineno == 1 and FRONTMATTER_FENCE.match(line):
            in_frontmatter = True
            continue
        if in_frontmatter:
            if FRONTMATTER_FENCE.match(line):
                in_frontmatter = False
            continue
        if CODE_FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield lineno, line


# Reconfigure on import so a guard that only does `from _common import …`
# is still covered before it calls ensure_utf8() explicitly.
ensure_utf8()
