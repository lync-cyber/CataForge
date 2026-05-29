"""Markdown structure parsing via markdown-it-py (headings, no regex pile)."""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=1)
def _md_parser():
    from markdown_it import MarkdownIt

    return MarkdownIt("commonmark")


def iter_markdown_headings(content: str) -> list[tuple[int, int, str]]:
    """Parse ATX headings; return ``(0-based line index, level 1–6, title text)``."""
    md = _md_parser()
    tokens = md.parse(content)
    out: list[tuple[int, int, str]] = []
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t.type == "heading_open" and t.map:
            level = int(t.tag[1]) if t.tag and len(t.tag) > 1 else 1
            line_start = t.map[0]
            title_parts: list[str] = []
            j = i + 1
            while j < n and tokens[j].type != "heading_close":
                if tokens[j].type == "inline" and tokens[j].content:
                    title_parts.append(tokens[j].content)
                j += 1
            title = " ".join(title_parts).strip()
            out.append((line_start, level, title))
        i += 1
    return out


def strip_code_blocks(text: str) -> str:
    """Drop fenced ```code``` spans so structural scans (xref, id extraction)
    don't match inside code samples."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def slice_section(text: str, anchor: str) -> str | None:
    """Return the heading slice matching ``anchor`` up to the next
    sibling-or-shallower heading (or EOF).

    ``anchor`` tolerates a leading ``§``. The marker is matched on word
    boundaries so ``"F-1"`` does not hit ``"F-12"``, and the slice end is
    the next heading at the same level or shallower, so a deeper sub-heading
    does not prematurely terminate the section.
    """
    lines = text.splitlines()
    marker = anchor.lstrip("§").strip()
    if not marker:
        return None
    boundary = r"(?:^|[^0-9A-Za-z_-])"
    after = r"(?=$|[^0-9A-Za-z_-])"
    pattern = re.compile(boundary + re.escape(marker) + after)
    start: int | None = None
    start_level = 0
    end = len(lines)
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            continue
        level = len(stripped) - len(stripped.lstrip("#"))
        if start is None:
            if pattern.search(line):
                start = i
                start_level = level
            continue
        if level <= start_level:
            end = i
            break
    if start is None:
        return None
    return "\n".join(lines[start:end])
