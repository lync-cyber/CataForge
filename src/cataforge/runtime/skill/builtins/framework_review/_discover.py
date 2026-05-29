"""Filesystem discovery + YAML frontmatter parse helpers."""

from __future__ import annotations

from pathlib import Path

from cataforge.utils.frontmatter import split_yaml_frontmatter


def discover_agents(root: Path) -> dict[str, Path]:
    base = root / ".cataforge" / "agents"
    if not base.is_dir():
        return {}
    return {
        d.name: d / "AGENT.md"
        for d in base.iterdir()
        if d.is_dir() and (d / "AGENT.md").is_file()
    }


def discover_skills(root: Path) -> dict[str, Path]:
    base = root / ".cataforge" / "skills"
    if not base.is_dir():
        return {}
    return {
        d.name: d / "SKILL.md"
        for d in base.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    }


def discover_agent_protocol_docs(root: Path) -> list[tuple[str, Path]]:
    """Companion ``*PROTOCOL*.md`` docs under ``.cataforge/agents/<id>/``.

    CLAUDE.md §硬约束 1 lists these alongside AGENT.md / SKILL.md as
    prompt-context loaded on every dispatch — they must be subject to
    the same size threshold (B1-β) and content checks even though they
    aren't the agent's entry doc.
    """
    base = root / ".cataforge" / "agents"
    if not base.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    for agent_dir in sorted(base.iterdir()):
        if not agent_dir.is_dir():
            continue
        for path in sorted(agent_dir.glob("*PROTOCOL*.md")):
            label = f"agents/{agent_dir.name}/{path.name}"
            found.append((label, path))
    return found


def parse_skills_field(content: str) -> list[str]:
    """Extract the ``skills:`` list from a YAML frontmatter block."""
    fm, _ = split_yaml_frontmatter(content)
    if not fm:
        return []
    raw = fm.get("skills") or []
    if isinstance(raw, str):
        raw = [s.strip() for s in raw.split(",") if s.strip()]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            item = item.split("#", 1)[0].strip()
            if item:
                out.append(item)
    return out


def parse_depends_field(content: str) -> list[str]:
    fm, _ = split_yaml_frontmatter(content)
    if not fm:
        return []
    raw = fm.get("depends") or []
    if isinstance(raw, str):
        raw = [s.strip() for s in raw.split(",") if s.strip()]
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]
