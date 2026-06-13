"""Phases 1 + 2: enumerate business docs and parse structure.

`scan_business_docs(project_root, doc_types)` walks the project's
`docs/{subdir}/*.md` tree for each in-scope doc_type and returns one
`ParsedDoc` per file with frontmatter, heading layout, and source mtime.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cataforge.domain.docs.index_ops import _load_doc_type_map
from cataforge.domain.kg.ingest.frontmatter import _PARSE_ERROR_KEY, parse_frontmatter
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
    source_path: str = ""  # project-root-relative posix path of the source file
    frontmatter: dict[str, Any] = field(default_factory=dict)
    sections: list[HeadingSpan] = field(default_factory=list)
    code_block_offsets: list[tuple[int, int]] = field(default_factory=list)

    @property
    def frontmatter_raw(self) -> str:
        """The original frontmatter block (and trailing newline) verbatim.

        The prefix of `raw` that precedes `body`; empty when the file has
        no frontmatter. Preserves byte-exact field order and formatting for
        whole-document reconstruction.
        """
        return self.raw[: len(self.raw) - len(self.body)] if self.body else ""


def _build_line_offsets(text: str) -> list[int]:
    """Return cumulative character offsets for the start of each line (0-based)."""
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _code_block_char_ranges(raw: str) -> list[tuple[int, int]]:
    """Return character ``(start, end)`` ranges for fenced code, inline code, and HTML blocks.

    Uses markdown-it-py token maps (line-based) and converts them to character
    offsets via the cumulative-line-offset table so callers can test
    ``start <= char_offset < end`` without parsing tokens a second time.
    """
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark")
    tokens = md.parse(raw)
    line_offsets = _build_line_offsets(raw)

    ranges: list[tuple[int, int]] = []

    def _add(token_map: list[int] | None) -> None:
        if token_map and len(token_map) >= 2:
            start_line, end_line = token_map[0], token_map[1]
            start_char = line_offsets[start_line] if start_line < len(line_offsets) else len(raw)
            end_char = line_offsets[end_line] if end_line < len(line_offsets) else len(raw)
            ranges.append((start_char, end_char))

    for token in tokens:
        if token.type in ("fence", "code_block", "html_block"):
            _add(token.map)
        # Recurse into inline tokens for code_inline children.
        if token.children:
            for child in token.children:
                if child.type == "code_inline" and token.map:
                    # code_inline has no map of its own; approximate from parent token map.
                    # Build precise char range by searching for the backtick-wrapped span.
                    parent_start = (
                        line_offsets[token.map[0]] if token.map[0] < len(line_offsets) else len(raw)
                    )
                    parent_end = (
                        line_offsets[token.map[1]] if token.map[1] < len(line_offsets) else len(raw)
                    )
                    parent_text = raw[parent_start:parent_end]
                    # Find each occurrence of `child.content` wrapped in backticks.
                    import re as _re

                    for m in _re.finditer(r"`" + _re.escape(child.content) + r"`", parent_text):
                        ranges.append((parent_start + m.start(), parent_start + m.end()))

    return ranges


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


def parse_doc_text(
    raw: str,
    *,
    doc_type: str,
    file_name: str,
    source_path: str,
    mtime: float,
    file_path: Path | None = None,
) -> ParsedDoc:
    """Parse one Markdown document's raw text into a ``ParsedDoc``.

    A malformed frontmatter block yields a ``ParsedDoc`` whose ``frontmatter``
    carries ``__parse_error__``; the caller decides whether to skip or raise.
    ``doc_id`` / ``doc_type`` derive from the frontmatter when present, else
    from ``file_name`` and the passed ``doc_type``.
    """
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    frontmatter, body = parse_frontmatter(raw)
    if _PARSE_ERROR_KEY in frontmatter:
        return ParsedDoc(
            doc_id=_infer_doc_id(file_name, doc_type),
            doc_type=doc_type,
            file_path=file_path or Path(source_path),
            mtime=mtime,
            raw=raw,
            body=body,
            body_offset=0,
            source_path=source_path,
            frontmatter=frontmatter,
        )
    body_offset = raw.count("\n", 0, len(raw) - len(body)) if body else 0
    doc_id = frontmatter.get("doc_id") or _infer_doc_id(file_name, doc_type)
    ft_doc_type = frontmatter.get("doc_type") or doc_type
    return ParsedDoc(
        doc_id=doc_id,
        doc_type=ft_doc_type,
        file_path=file_path or Path(source_path),
        mtime=mtime,
        raw=raw,
        body=body,
        body_offset=body_offset,
        source_path=source_path,
        frontmatter=frontmatter,
        sections=_heading_spans(body, body_offset),
        code_block_offsets=_code_block_char_ranges(raw),
    )


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
            raw = path.read_text()
            doc = parse_doc_text(
                raw,
                doc_type=doc_type,
                file_name=path.name,
                source_path=path.relative_to(project_root).as_posix(),
                mtime=path.stat().st_mtime,
                file_path=path,
            )
            if _PARSE_ERROR_KEY in doc.frontmatter:
                warnings.warn(
                    f"Skipping {path} due to frontmatter YAML parse error",
                    category=UserWarning,
                    stacklevel=2,
                )
                continue
            parsed.append(doc)
    return parsed
