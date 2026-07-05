"""Shared markdown structure helpers — H2 section splitting and pipe tables."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass

_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


@dataclass(frozen=True)
class MarkdownTable:
    """A parsed GitHub-flavored pipe table.

    ``rows`` are returned verbatim (not padded to ``len(headers)``) so callers
    can index by column and still detect short rows.
    """

    headers: list[str]
    rows: list[list[str]]


def _split_table_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [cell.strip() for cell in s.split("|")]


def parse_markdown_table(text: str) -> MarkdownTable | None:
    """Return the first GFM pipe table in *text*, or ``None`` when none exists.

    A table is a header row, a ``---`` separator row, then zero or more
    pipe-delimited data rows; leading/trailing pipes are optional and cells are
    stripped. Scanning stops at the first blank or non-pipe line after the data.
    """
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        if "|" not in lines[i] or _TABLE_SEP_RE.match(lines[i]):
            continue
        if not _TABLE_SEP_RE.match(lines[i + 1]):
            continue
        headers = _split_table_row(lines[i])
        rows: list[list[str]] = []
        for line in lines[i + 2 :]:
            if not line.strip() or "|" not in line:
                break
            if _TABLE_SEP_RE.match(line):
                continue
            rows.append(_split_table_row(line))
        return MarkdownTable(headers=headers, rows=rows)
    return None


def split_h2_sections(text: str, h2_re: re.Pattern[str]) -> tuple[str, OrderedDict[str, str]]:
    """Split markdown into ``(preamble_before_first_h2, OrderedDict[title, body])``.

    Sections are delimited by *h2_re* — a compiled ``^## `` matcher with a
    ``title`` group. Callers pass their own pattern because the exact
    trailing-whitespace handling differs by use case. A single leading newline
    on each body is normalized away.
    """
    matches = list(h2_re.finditer(text))
    if not matches:
        return text, OrderedDict()

    preamble = text[: matches[0].start()]
    sections: OrderedDict[str, str] = OrderedDict()
    for i, m in enumerate(matches):
        title = m.group("title").strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        if body.startswith("\n"):
            body = body[1:]
        sections[title] = body
    return preamble, sections
