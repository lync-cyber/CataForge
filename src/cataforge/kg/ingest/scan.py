"""Phases 1 + 2: enumerate business docs and parse structure.

`scan_business_docs(project_root, doc_types)` walks the project's
`docs/{subdir}/*.md` tree for each in-scope doc_type and returns one
`ParsedDoc` per file with frontmatter, heading layout, and source mtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cataforge.docs.loader import _load_doc_type_map
from cataforge.kg.ingest.frontmatter import parse_frontmatter
from cataforge.utils.md_parse import iter_markdown_headings


@dataclass
class HeadingSpan:
    """A heading plus the line range of its section body.

    `line_start` is the heading's own line (0-based). `line_end` is the
    line immediately before the next heading at the same or higher level
    (or the end of the file for the last section).
    """

    line_start: int
    line_end: int
    level: int
    title: str


@dataclass
class ParsedDoc:
    """A single business-doc Markdown file, parsed but not yet entity-extracted."""

    doc_id: str
    doc_type: str
    file_path: Path
    mtime: float
    raw: str
    body: str
    body_offset: int  # line index where `body` starts inside `raw`
    frontmatter: dict[str, Any] = field(default_factory=dict)
    sections: list[HeadingSpan] = field(default_factory=list)


def _heading_spans(body: str, body_offset: int) -> list[HeadingSpan]:
    headings = iter_markdown_headings(body)
    if not headings:
        return []
    total_lines = body.count("\n") + 1
    spans: list[HeadingSpan] = []
    for i, (line_idx, level, title) in enumerate(headings):
        end = total_lines
        for next_line, next_level, _ in headings[i + 1 :]:
            if next_level <= level:
                end = next_line
                break
        spans.append(
            HeadingSpan(
                line_start=line_idx + body_offset,
                line_end=end + body_offset,
                level=level,
                title=title,
            )
        )
    return spans


def _infer_doc_id(file_name: str, doc_type: str) -> str:
    """`prd-{project}.md` → `prd`; fall back to the stem with the doc_type prefix stripped."""
    stem = Path(file_name).stem
    if stem == doc_type or stem.startswith(f"{doc_type}-"):
        return doc_type
    return stem


def scan_business_docs(
    project_root: Path,
    doc_types: list[str],
) -> list[ParsedDoc]:
    """Phase 1+2: enumerate + parse all in-scope business docs.

    Files without a closable frontmatter block are still returned (with an
    empty frontmatter dict) so downstream phases can decide policy.
    """
    project_root = Path(project_root)
    type_map = _load_doc_type_map(str(project_root))

    parsed: list[ParsedDoc] = []
    for doc_type in doc_types:
        subdir = type_map.get(doc_type, doc_type)
        directory = project_root / "docs" / subdir
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(raw)
            body_offset = raw.count("\n", 0, len(raw) - len(body)) if body else 0
            doc_id = frontmatter.get("doc_id") or _infer_doc_id(path.name, doc_type)
            ft_doc_type = frontmatter.get("doc_type") or doc_type
            parsed.append(
                ParsedDoc(
                    doc_id=doc_id,
                    doc_type=ft_doc_type,
                    file_path=path,
                    mtime=path.stat().st_mtime,
                    raw=raw,
                    body=body,
                    body_offset=body_offset,
                    frontmatter=frontmatter,
                    sections=_heading_spans(body, body_offset),
                )
            )
    return parsed
