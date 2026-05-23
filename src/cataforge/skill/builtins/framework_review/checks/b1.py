"""B1 — required-section + size-threshold checks."""

from __future__ import annotations

import re
from pathlib import Path

from .._constants import (
    B1_REQUIRED_SECTIONS_EXEMPT_AGENTS,
    B1_REQUIRED_SECTIONS_EXEMPT_SKILLS,
    REQUIRED_SECTIONS_AGENT,
    REQUIRED_SECTIONS_SKILL,
)
from .._discover import (
    discover_agent_protocol_docs,
    discover_agents,
    discover_skills,
)
from .._types import Report


def check_b1_required_sections(
    root: Path, scope: str, report: Report
) -> None:
    """B1-α: required structural sections in AGENT.md / SKILL.md."""
    targets: list[tuple[str, Path, dict[str, str]]] = []
    if scope in ("agents", "all"):
        for aid, path in discover_agents(root).items():
            if aid in B1_REQUIRED_SECTIONS_EXEMPT_AGENTS:
                continue
            targets.append((f"agents/{aid}", path, REQUIRED_SECTIONS_AGENT))
    if scope in ("skills", "all"):
        for sid, path in discover_skills(root).items():
            if sid in B1_REQUIRED_SECTIONS_EXEMPT_SKILLS:
                continue
            targets.append((f"skills/{sid}", path, REQUIRED_SECTIONS_SKILL))

    for label, path, required in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            report.add("B1_required_sections", "FAIL", label, f"cannot read: {exc}")
            continue
        for sect_name, pattern in required.items():
            if not re.search(pattern, text, re.MULTILINE):
                report.add(
                    "B1_required_sections",
                    "FAIL",
                    label,
                    f"missing section: {sect_name}",
                )


def check_b1_size(
    root: Path, scope: str, threshold: int, report: Report
) -> None:
    """B1-β: META_DOC_SPLIT_THRESHOLD_LINES soft cap.

    Covers every prompt-context file enumerated in CLAUDE.md §硬约束 1:
    AGENT.md, SKILL.md, agents/<id>/*PROTOCOL*.md companion docs, and
    rules/*.md.
    """
    targets: list[tuple[str, Path]] = []
    if scope in ("agents", "all"):
        for aid, path in discover_agents(root).items():
            targets.append((f"agents/{aid}", path))
        targets.extend(discover_agent_protocol_docs(root))
    if scope in ("skills", "all"):
        for sid, path in discover_skills(root).items():
            targets.append((f"skills/{sid}", path))
    if scope in ("rules", "all"):
        rules_dir = root / ".cataforge" / "rules"
        if rules_dir.is_dir():
            for path in sorted(rules_dir.rglob("*.md")):
                try:
                    rel = path.relative_to(root).as_posix()
                except ValueError:
                    rel = str(path)
                targets.append((rel, path))

    for label, path in targets:
        try:
            line_count = sum(1 for _ in path.open(encoding="utf-8"))
        except OSError:
            continue
        if line_count > threshold:
            report.add(
                "B1_size_threshold",
                "WARN",
                label,
                f"{line_count} lines > META_DOC_SPLIT_THRESHOLD_LINES "
                f"({threshold}); 建议拆分为分卷",
            )
