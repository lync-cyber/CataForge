"""Markdown structure parsing via markdown-it-py (headings, no regex pile)."""

from __future__ import annotations

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
