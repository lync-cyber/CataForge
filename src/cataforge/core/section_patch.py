"""Section-level patching for markdown assets (AGENT.md / SKILL.md / siblings).

An override layer can ship a ``<name>.patch.md`` next to a base ``<name>.md``.
The patch is a markdown file whose ``## `` (H2) sections are merged onto the
base:

* a patch section whose title matches a base section **replaces** that
  section's body (override an existing section);
* a patch section whose title is new is **appended** after the base sections
  (add a custom section).

Only H2 headings delimit sections; ``###`` and deeper headings live inside
their parent H2 body and travel with it, so replacing ``## Phase Routing``
swaps the whole block including its subsections.

Content before the first H2 (frontmatter, the H1 title, intro prose) is the
*preamble*. A patch does not touch the base preamble — frontmatter changes are
a whole-file override's job, not a section patch's. The one exception: when the
base is empty (a brand-new asset created entirely from a patch) the patch is
returned verbatim.
"""

from __future__ import annotations

import re
from collections import OrderedDict

_H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)


def apply_section_patch(base: str, patch: str) -> str:
    """Merge *patch*'s H2 sections onto *base*. See module docstring."""
    if not base.strip():
        return patch

    preamble, sections = _split(base)
    _, patch_sections = _split(patch)
    if not patch_sections:
        return base

    for title, body in patch_sections.items():
        sections[title] = body  # replace existing, or append new (insertion order)

    return _serialize(preamble, sections)


def section_bodies(text: str) -> OrderedDict[str, str]:
    """Return ``OrderedDict[title, body]`` of *text*'s H2 sections (no preamble)."""
    _, sections = _split(text)
    return sections


def patched_sections(base: str, patch: str) -> tuple[list[str], list[str]]:
    """Return ``(overridden_titles, added_titles)`` a patch would apply.

    Pure inspection helper for tooling / dry-run reporting — does not mutate.
    """
    _, base_sections = _split(base)
    _, patch_sections = _split(patch)
    overridden = [t for t in patch_sections if t in base_sections]
    added = [t for t in patch_sections if t not in base_sections]
    return overridden, added


def _split(text: str) -> tuple[str, OrderedDict[str, str]]:
    """Split markdown into ``(preamble, OrderedDict[title, body])`` on H2."""
    matches = list(_H2_RE.finditer(text))
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


def _serialize(preamble: str, sections: OrderedDict[str, str]) -> str:
    """Rebuild markdown, keeping heading-to-body newline discipline."""
    out = [preamble]
    for title, body in sections.items():
        if out[-1] and not out[-1].endswith("\n"):
            out.append("\n")
        out.append(f"## {title}\n")
        out.append(body)
        if not body.endswith("\n"):
            out.append("\n")
    return "".join(out)
