"""CLAUDE.md hygiene — Learnings Registry compaction + state bloat diagnostics.

CLAUDE.md is the per-project instruction file deploy emits / merges. Runtime
state can bloat in two different ways:

* **§项目状态 → Learnings Registry** is a free-form bullet list orchestrator
  appends to. This module can compact it safely because entries are list-shaped.
* **§项目状态 schema bullets** such as ``上次完成`` / ``下一步行动`` can also grow
  into run-on history lines. They are live state, so this module measures and
  warns about overlong bullets but does not rewrite them automatically.

State history belongs in durable records such as ``docs/EVENT-LOG.jsonl``,
``docs/reviews/`` or ``docs/changelog/``; the instruction file keeps only the
short live handoff.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cataforge.utils.atomic_write import atomic_write_text

# H2 heading we look for in CLAUDE.md. Allow trailing parenthetical
# annotations like "项目状态 (orchestrator专属写入区，其他Agent禁止修改)".
_PROJECT_STATE_H2_RE = re.compile(
    r"^##\s+项目状态(?:\s*\([^)]*\))?\s*$",
    re.MULTILINE,
)
_NEXT_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
_LEARNINGS_FIELD_RE = re.compile(
    r"^- Learnings Registry:[ \t]*(?P<inline>[^\n]*)(?P<children>(?:\n {2,}-[^\n]*)*)",
    re.MULTILINE,
)


@dataclass
class ClaudeMdMeasurement:
    """Snapshot of CLAUDE.md size + per-section bloat indicators."""

    path: Path
    exists: bool
    total_bytes: int
    total_lines: int
    state_section_lines: int
    learnings_entries: int
    max_state_bullet_chars: int


def measure_claude_md(claude_md_path: Path) -> ClaudeMdMeasurement:
    """Return a :class:`ClaudeMdMeasurement` for the given CLAUDE.md path.

    Returns ``exists=False`` with zero counts when the file is missing —
    ``cataforge doctor`` skips the WARN in that case.
    """
    if not claude_md_path.is_file():
        return ClaudeMdMeasurement(
            path=claude_md_path,
            exists=False,
            total_bytes=0,
            total_lines=0,
            state_section_lines=0,
            learnings_entries=0,
            max_state_bullet_chars=0,
        )
    text = claude_md_path.read_text()
    total_bytes = len(text.encode("utf-8"))
    total_lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)

    state_lines, longest_bullet, registry_inline, registry_children = _extract_state_section(text)

    learnings_entries = _count_registry_entries(registry_inline, registry_children)

    return ClaudeMdMeasurement(
        path=claude_md_path,
        exists=True,
        total_bytes=total_bytes,
        total_lines=total_lines,
        state_section_lines=state_lines,
        learnings_entries=learnings_entries,
        max_state_bullet_chars=longest_bullet,
    )


@dataclass
class CompactionResult:
    """Outcome of one ``compact_learnings_registry`` run."""

    archived_entries: int
    kept_entries: int
    archive_path: Path
    rewrote_claude_md: bool


def compact_learnings_registry(
    claude_md_path: Path,
    *,
    archive_path: Path,
    max_entries: int,
) -> CompactionResult:
    """Trim Learnings Registry in CLAUDE.md to the latest ``max_entries`` items.

    Archived entries are appended to ``archive_path`` with a
    ``## YYYY-MM-DD`` header so future re-runs don't duplicate. The rewrite
    is idempotent: if ``len(entries) <= max_entries`` the file is not
    touched and ``rewrote_claude_md`` is False.

    Args:
        claude_md_path: project CLAUDE.md to mutate in place.
        archive_path: destination for trimmed entries; created on first run.
        max_entries: how many of the most recent entries to keep inline.

    Returns:
        CompactionResult describing what changed.
    """
    if max_entries < 0:
        raise ValueError(f"max_entries must be >= 0, got {max_entries}")
    if not claude_md_path.is_file():
        return CompactionResult(
            archived_entries=0,
            kept_entries=0,
            archive_path=archive_path,
            rewrote_claude_md=False,
        )

    text = claude_md_path.read_text()
    match = _LEARNINGS_FIELD_RE.search(text)
    if match is None:
        return CompactionResult(
            archived_entries=0,
            kept_entries=0,
            archive_path=archive_path,
            rewrote_claude_md=False,
        )

    inline = (match.group("inline") or "").strip()
    children_block = match.group("children") or ""
    entries = _split_registry_entries(inline, children_block)

    if len(entries) <= max_entries:
        return CompactionResult(
            archived_entries=0,
            kept_entries=len(entries),
            archive_path=archive_path,
            rewrote_claude_md=False,
        )

    # Treat the list as chronologically ordered (oldest first). Archive the
    # head; keep the tail. Orchestrator appends new entries at the bottom,
    # so this matches insertion order without extra timestamping.
    keep_count = max_entries
    archive_entries = entries[: len(entries) - keep_count]
    keep_entries = entries[len(entries) - keep_count :]

    new_field = _render_registry_field(keep_entries)
    new_text = text[: match.start()] + new_field + text[match.end() :]

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    _append_archive(archive_path, archive_entries)
    atomic_write_text(claude_md_path, new_text)

    return CompactionResult(
        archived_entries=len(archive_entries),
        kept_entries=len(keep_entries),
        archive_path=archive_path,
        rewrote_claude_md=True,
    )


# ─── internals ────────────────────────────────────────────────────────────────


def _extract_state_section(text: str) -> tuple[int, int, str, str]:
    """Return (state_lines, longest_bullet_chars, registry_inline, registry_children)."""
    head_match = _PROJECT_STATE_H2_RE.search(text)
    if not head_match:
        return 0, 0, "", ""
    section_start = head_match.end()
    next_h2 = _NEXT_H2_RE.search(text, pos=section_start)
    section_end = next_h2.start() if next_h2 else len(text)
    section_body = text[section_start:section_end]
    state_lines = section_body.count("\n")
    longest_bullet = _longest_bullet_chars(section_body)

    field = _LEARNINGS_FIELD_RE.search(section_body)
    if field is None:
        return state_lines, longest_bullet, "", ""
    return (
        state_lines,
        longest_bullet,
        (field.group("inline") or ""),
        (field.group("children") or ""),
    )


def _longest_bullet_chars(section_body: str) -> int:
    """Longest bullet line in a section, measured by stripped length (0 if none).

    Catches the single-bullet run-on bloat the line-count limit misses: a status
    field that accumulates closed-PR history into one ever-growing line keeps the
    line count flat while the character count explodes.
    """
    lengths = [
        len(stripped)
        for line in section_body.splitlines()
        if (stripped := line.strip()).startswith("-")
    ]
    return max(lengths, default=0)


def _split_registry_entries(inline: str, children_block: str) -> list[str]:
    """Parse a Learnings Registry field body into a flat list of entries.

    Two supported shapes:

    * Inline single-line: ``- Learnings Registry: foo; bar; baz`` →
      treats ``;`` as separator, drops empty fragments.
    * Bullet children: ::

          - Learnings Registry:
            - 2026-04-01 retro skipped (below threshold)
            - 2026-04-15 adaptive-review downgraded for development

      → each child line is one entry.

    Mixed (inline + children) is also tolerated.
    """
    entries: list[str] = []
    inline_stripped = inline.strip()
    if inline_stripped:
        # Skip explicit "(empty)" / "—" / "首次 retrospective 后填充" placeholders.
        placeholder_markers = ("(empty)", "—", "首次 retrospective 后填充")
        if not any(p in inline_stripped for p in placeholder_markers):
            for fragment in re.split(r"[;；]", inline_stripped):
                fragment = fragment.strip()
                if fragment:
                    entries.append(fragment)
    for line in children_block.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        entry = line.lstrip("-").strip()
        if entry:
            entries.append(entry)
    return entries


def _count_registry_entries(inline: str, children_block: str) -> int:
    return len(_split_registry_entries(inline, children_block))


def _render_registry_field(entries: list[str]) -> str:
    """Re-render the Learnings Registry field with the given entries.

    Uses bullet-children form regardless of the original shape — gives
    orchestrator a consistent target to append to and is easier for
    humans to scan.
    """
    if not entries:
        return (
            "- Learnings Registry: (compacted; archive in .cataforge/learnings/registry-archive.md)"
        )
    lines = ["- Learnings Registry:"]
    for e in entries:
        lines.append(f"  - {e}")
    return "\n".join(lines)


def _append_archive(archive_path: Path, archive_entries: list[str]) -> None:
    """Append ``archive_entries`` under a today-stamped section in archive_path."""
    today = date.today().isoformat()
    header = f"\n## {today}\n"
    body_lines = [f"- {e}" for e in archive_entries]
    chunk = header + "\n".join(body_lines) + "\n"

    if archive_path.is_file():
        existing = archive_path.read_text()
        if not existing.endswith("\n"):
            existing += "\n"
        atomic_write_text(archive_path, existing + chunk)
    else:
        preamble = (
            "# Learnings Registry — archive\n\n"
            "<!-- author: claude-md-hygiene · auto-archived from CLAUDE.md -->\n"
            "<!-- Each section header (## YYYY-MM-DD) marks one compaction batch. -->\n"
        )
        atomic_write_text(archive_path, preamble + chunk)


__all__ = [
    "ClaudeMdMeasurement",
    "CompactionResult",
    "compact_learnings_registry",
    "measure_claude_md",
]
