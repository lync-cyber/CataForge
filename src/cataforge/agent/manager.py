"""Agent manager — discovery, listing, validation."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.core.types import CAPABILITY_IDS

_FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)


def _parse_tools_from_frontmatter(content: str) -> list[str] | None:
    """Extract the ``tools`` list from YAML frontmatter, supporting both
    block-style and flow-style (``tools: [a, b]``).

    Returns ``None`` when no ``tools`` key is present.
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    raw = fm.get("tools")
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


class AgentManager:
    """Discover and validate agent definitions."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())

    def list_agents(self) -> list[str]:
        """Return sorted list of agent IDs."""
        agents_dir = self._paths.agents_dir
        if not agents_dir.is_dir():
            return []
        return sorted(
            d.name for d in agents_dir.iterdir() if d.is_dir() and (d / "AGENT.md").is_file()
        )

    def validate(self, agent_id: str | None = None) -> list[str]:
        """Validate agent definitions. Returns list of issues."""
        issues: list[str] = []
        agents = [agent_id] if agent_id else self.list_agents()

        for aid in agents:
            agent_md = self._paths.agent_dir(aid) / "AGENT.md"
            if not agent_md.is_file():
                issues.append(f"{aid}: AGENT.md not found")
                continue
            issues.extend(self._validate_agent(aid, agent_md))

        return issues

    def _validate_agent(self, agent_id: str, agent_md: Path) -> list[str]:
        issues: list[str] = []
        content = agent_md.read_text(encoding="utf-8")

        # Check frontmatter exists
        if not content.startswith("---"):
            issues.append(f"{agent_id}: missing YAML frontmatter")
            return issues

        # Check tools use capability IDs (not platform-native names)
        tool_names = _parse_tools_from_frontmatter(content)
        if tool_names is not None:
            for tn in tool_names:
                if tn and tn not in CAPABILITY_IDS:
                    issues.append(
                        f"{agent_id}: tool '{tn}' is not a capability ID "
                        f"(expected one of {CAPABILITY_IDS})"
                    )

        return issues

    def get_agent_content(self, agent_id: str) -> str | None:
        agent_md = self._paths.agent_dir(agent_id) / "AGENT.md"
        if agent_md.is_file():
            return agent_md.read_text(encoding="utf-8")
        return None
