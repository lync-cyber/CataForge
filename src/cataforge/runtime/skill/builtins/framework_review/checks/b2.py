"""B2 — cross-reference graph completeness."""

from __future__ import annotations

from pathlib import Path

from .._constants import ORPHAN_SKILL_WHITELIST
from .._discover import (
    discover_agents,
    discover_skills,
    parse_depends_field,
    parse_skills_field,
)
from .._types import Report


def check_b2_cross_references(root: Path, report: Report) -> None:
    """B2-α: skills referenced in AGENT.md / SKILL.md must resolve."""
    agents = discover_agents(root)
    skills = discover_skills(root)

    try:
        from cataforge.runtime.skill.loader import SkillLoader

        loader = SkillLoader(project_root=root)
        for meta in loader.discover():
            if meta.id not in skills:
                skills[meta.id] = Path("(builtin)")
    except Exception:
        pass

    referenced: dict[str, set[str]] = {}

    for aid, path in agents.items():
        try:
            content = path.read_text()
        except OSError:
            continue
        for skill_id in parse_skills_field(content):
            referenced.setdefault(skill_id, set()).add(f"agents/{aid}")

    for sid, path in skills.items():
        if not path.is_file():
            continue
        try:
            content = path.read_text()
        except OSError:
            continue
        for dep_id in parse_depends_field(content):
            referenced.setdefault(dep_id, set()).add(f"skills/{sid}")

    for skill_id, refs in sorted(referenced.items()):
        if skill_id not in skills:
            for ref in sorted(refs):
                report.add(
                    "B2_cross_reference_graph",
                    "FAIL",
                    ref,
                    f"references missing skill/agent: {skill_id!r}",
                )

    for skill_id in sorted(skills):
        if skill_id in ORPHAN_SKILL_WHITELIST:
            continue
        if skill_id not in referenced:
            report.add(
                "B2_cross_reference_graph",
                "WARN",
                f"skills/{skill_id}",
                "orphan skill: not referenced by any AGENT.md.skills "
                "or SKILL.md.depends",
            )
