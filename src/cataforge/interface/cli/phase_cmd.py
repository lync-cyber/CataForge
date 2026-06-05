"""cataforge phase — read-only inspection of a project's workflow phase.

Distinguishes "framework deployed" from "workflow actually driven": a fresh
deploy leaves the instruction file's 当前阶段 as a placeholder with no docs,
no EVENT-LOG, no index. ``phase status`` checks the current phase's expected
artifacts exist and exits non-zero when they don't, giving orchestration a
machine-checkable phase boundary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from cataforge.adapter.platform.registry import parse_current_phase, resolve_instruction_file
from cataforge.core.errors import CataforgeError
from cataforge.interface.cli.helpers import resolve_root
from cataforge.interface.cli.main import cli
from cataforge.utils.frontmatter import split_yaml_frontmatter

# Recognised 当前阶段 values across all execution modes — the union of the
# standard 7-phase sequence with the agile merged phases (``planning`` for
# agile-lite, fusing requirements+architecture; ``brief`` for agile-prototype,
# fusing Phase 1–4). Membership is a recognition gate; ordering carries no
# semantics.
PHASES: tuple[str, ...] = (
    "brief",
    "planning",
    "requirements",
    "architecture",
    "ui_design",
    "dev_planning",
    "development",
    "testing",
    "deployment",
    "completed",
)

# Each gated phase's expected primary document(s) (base doc_type; the ``-lite``
# variant is accepted under agile modes). A tuple gates on every listed
# doc_type. Phases absent here carry no document gate (development is code-only;
# completed is terminal). The agile merged ``planning`` phase fuses
# requirements+architecture, so it gates on both prd and arch; ``brief``
# produces the single agile-prototype doc.
PHASE_DOC_TYPE: dict[str, str | tuple[str, ...]] = {
    "brief": "brief",
    "planning": ("prd", "arch"),
    "requirements": "prd",
    "architecture": "arch",
    "ui_design": "ui-spec",
    "dev_planning": "dev-plan",
    "testing": "test-report",
    "deployment": "deploy-spec",
}

_NOT_STARTED = "未开始"


def is_placeholder(value: str | None) -> bool:
    """True when 当前阶段 is unfilled (the ``{a|b|c}`` template token)."""
    return not value or "{" in value or "|" in value


def parse_doc_status(state_text: str) -> dict[str, str]:
    """Parse the ``文档状态`` block into ``{doc_type: status}``."""
    out: dict[str, str] = {}
    in_block = False
    for line in state_text.splitlines():
        if re.match(r"^-\s*文档状态:", line):
            in_block = True
            continue
        if not in_block:
            continue
        m = re.match(r"^\s+-\s*([a-z][a-z-]*):\s*(.+?)\s*$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
        elif line.strip() and not line.startswith(" "):
            break
    return out


def parse_phase_starts(eventlog_text: str) -> set[str]:
    """Phases that have a ``phase_start`` record in EVENT-LOG.jsonl."""
    phases: set[str] = set()
    for line in eventlog_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("event") == "phase_start" and rec.get("phase"):
            phases.add(str(rec["phase"]))
    return phases


def indexed_doc_types(index_text: str) -> set[str]:
    """Base doc_types present in a .doc-index.json document map."""
    try:
        data = json.loads(index_text)
    except json.JSONDecodeError:
        return set()
    docs = data.get("documents", {})
    if not isinstance(docs, dict):
        return set()
    return {
        str(d.get("doc_type")) for d in docs.values() if isinstance(d, dict) and d.get("doc_type")
    }


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _frontmatter_doc_type(path: Path) -> str | None:
    """Return a Markdown file's frontmatter ``doc_type``, or None when absent."""
    fm, _ = split_yaml_frontmatter(_read(path))
    if not fm:
        return None
    value = fm.get("doc_type")
    return value if isinstance(value, str) else None


def _find_phase_doc(docs_dir: Path, doc_type: str) -> Path | None:
    """Locate a phase's primary doc under ``docs/{doc_type}/``.

    context generate writes ``docs/{doc_type}/{template_id}-{project}.md``; the
    subdir name is the doc_type, so any ``*.md`` under it belongs to this family
    (lite variants and split volumes included). A subdir file that *explicitly*
    declares a different frontmatter doc_type is excluded so a misplaced doc
    can't satisfy the gate; files with no declared type are trusted by location.
    Flat ``docs/{doc_type}(-lite).md`` are a backward-compat fallback.
    """
    subdir = docs_dir / doc_type
    subdir_mds = sorted(subdir.glob("*.md")) if subdir.is_dir() else []
    candidates = [p for p in subdir_mds if _frontmatter_doc_type(p) in (None, doc_type)]
    candidates += [docs_dir / f"{doc_type}.md", docs_dir / f"{doc_type}-lite.md"]
    return next((c for c in candidates if c.is_file()), None)


def evaluate_phase(root: Path) -> tuple[str | None, list[tuple[str, bool, str]]]:
    """Evaluate the current phase's expected artifacts.

    Returns ``(current_phase, checks)`` where each check is
    ``(label, ok, detail)``. Raises :class:`CataforgeError` when the project
    has no readable instruction file (not a driven CataForge project).
    """
    state_path = resolve_instruction_file(root)
    if not state_path.is_file():
        err = CataforgeError(f"no {state_path.name} at {root}")
        err.exit_code = 2
        raise err

    state_text = _read(state_path)
    current = parse_current_phase(state_text)
    checks: list[tuple[str, bool, str]] = []

    if is_placeholder(current):
        checks.append(
            ("workflow driven", False, "当前阶段 is the placeholder token — workflow not driven")
        )
        return current, checks
    if current not in PHASES:
        checks.append(("phase recognised", False, f"当前阶段 {current!r} is not a known phase"))
        return current, checks

    checks.append(("phase recognised", True, current or ""))
    if current == "completed":
        return current, checks

    phase_starts = parse_phase_starts(_read(root / "docs" / "EVENT-LOG.jsonl"))
    checks.append(
        (
            "phase_start logged",
            current in phase_starts,
            "present" if current in phase_starts else "no phase_start event for this phase",
        )
    )

    doc_types = PHASE_DOC_TYPE.get(current)
    if doc_types is None:
        return current, checks
    if isinstance(doc_types, str):
        doc_types = (doc_types,)

    doc_status = parse_doc_status(state_text)
    docs_dir = root / "docs"
    indexed = indexed_doc_types(_read(docs_dir / ".doc-index.json"))
    for doc_type in doc_types:
        status = doc_status.get(doc_type, _NOT_STARTED)
        checks.append((f"{doc_type} doc status", status != _NOT_STARTED, status))

        found = _find_phase_doc(docs_dir, doc_type)
        checks.append(
            (
                f"{doc_type} doc present",
                found is not None,
                found.relative_to(root).as_posix()
                if found
                else f"docs/{doc_type}/*.md or docs/{doc_type}(-lite).md missing",
            )
        )

        is_indexed = doc_type in indexed
        checks.append(
            (
                f"{doc_type} indexed",
                is_indexed,
                "in .doc-index.json" if is_indexed else "absent (run cataforge docs index)",
            )
        )
    return current, checks


@cli.group("phase")
def phase_group() -> None:
    """Read-only inspection of a project's SDLC workflow phase."""


@phase_group.command("status")
def phase_status() -> None:
    """Verify the current phase's expected artifacts exist.

    Exit 0 when every check for the current phase passes; exit 1 when an
    expected artifact is missing (phase not driven, doc absent/unindexed, no
    phase_start); exit 2 when the project has no instruction file.
    """
    root = resolve_root()
    current, checks = evaluate_phase(root)

    click.echo(f"Phase: {current}")
    for label, ok, detail in checks:
        mark = "OK  " if ok else "FAIL"
        click.echo(f"  [{mark}] {label}: {detail}")

    failed = [label for label, ok, _ in checks if not ok]
    if failed:
        err = CataforgeError(
            f"phase {current!r}: {len(failed)} expected artifact(s) missing — " + ", ".join(failed)
        )
        err.exit_code = 1
        raise err
    click.echo(f"OK: phase {current!r} artifacts present")
