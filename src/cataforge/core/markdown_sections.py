"""Shared markdown H2 section splitting for section patch / merge."""

from __future__ import annotations

import re
from collections import OrderedDict


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
