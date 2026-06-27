"""Deploy reflects user/project override layers (P1).

Builds a minimal claude-code scaffold with a sectioned agent, drops a
section patch into an override layer, and asserts the deployed agent file
carries the override — proving the resolver is wired into deploy.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cataforge.adapter.platform.registry import clear_cache
from cataforge.core.config import ConfigManager
from cataforge.runtime.deploy.deployer import Deployer

_PROFILE: dict = {
    "platform_id": "claude-code",
    "display_name": "Claude Code",
    "tool_map": {"file_read": "Read", "file_edit": "Write"},
    "extended_capabilities": {},
    "agent_definition": {
        "format": "yaml-frontmatter",
        "scan_dirs": [".claude/agents"],
        "needs_deploy": True,
    },
    "instruction_file": {
        "reads_claude_md": True,
        "targets": [{"type": "project_state_copy", "path": "CLAUDE.md"}],
    },
    "dispatch": {"tool_name": "Agent", "is_async": False},
    "hooks": {"config_format": None, "config_path": None, "event_map": {}, "degradation": {}},
    "skill_definition": {"needs_deploy": True, "target_dir": ".claude/skills"},
    "command_definition": {"needs_deploy": True, "target_dir": ".claude/commands"},
}

_AGENT_MD = """\
---
name: architect
tools: file_read
---

# Role: Architect

## Identity
- base identity

## Execution Rules
- base rule one
- base rule two
"""


def _init_project(root: Path) -> Path:
    cf = root / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    (cf / "PROJECT-STATE.md").write_text("platform: {platform}\n", encoding="utf-8")
    (cf / "rules").mkdir()
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    (cf / "agents" / "architect").mkdir(parents=True)
    (cf / "agents" / "architect" / "AGENT.md").write_text(_AGENT_MD, encoding="utf-8")
    (cf / "hooks").mkdir()
    (cf / "hooks" / "hooks.yaml").write_text(
        "hooks: {}\ndegradation_templates: {}\n", encoding="utf-8"
    )
    (cf / "mcp").mkdir()
    (cf / "skills").mkdir()
    pdir = cf / "platforms" / "claude-code"
    pdir.mkdir(parents=True)
    (pdir / "profile.yaml").write_text(yaml.safe_dump(_PROFILE), encoding="utf-8")
    return root


def _deploy(root: Path) -> None:
    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")


def test_no_overrides_deploys_scaffold_agent(tmp_path: Path) -> None:
    _init_project(tmp_path)
    _deploy(tmp_path)
    deployed = (tmp_path / ".claude" / "agents" / "architect.md").read_text(encoding="utf-8")
    assert "base rule one" in deployed
    assert "base identity" in deployed


def test_project_override_section_patch_reaches_deploy(tmp_path: Path) -> None:
    _init_project(tmp_path)
    patch_dir = tmp_path / ".cataforge" / "overrides" / "project" / "agents" / "architect"
    patch_dir.mkdir(parents=True)
    (patch_dir / "AGENT.patch.md").write_text(
        "## Execution Rules\n- overridden rule\n\n## Project Conventions\n- team-only section\n",
        encoding="utf-8",
    )

    _deploy(tmp_path)

    deployed = (tmp_path / ".claude" / "agents" / "architect.md").read_text(encoding="utf-8")
    # Existing section overridden.
    assert "overridden rule" in deployed
    assert "base rule one" not in deployed
    # New custom section added.
    assert "## Project Conventions" in deployed
    assert "team-only section" in deployed
    # Untouched section + frontmatter preserved.
    assert "base identity" in deployed
    assert "name: architect" in deployed


def test_plugin_agent_materialises_in_deploy(tmp_path: Path) -> None:
    _init_project(tmp_path)
    # A local plugin provides a brand-new agent.
    pdir = tmp_path / ".cataforge" / "plugins" / "p1"
    (pdir / "agents" / "scribe").mkdir(parents=True)
    (pdir / "cataforge-plugin.yaml").write_text(
        yaml.safe_dump({"id": "p1", "provides": {"agents": ["scribe"]}}),
        encoding="utf-8",
    )
    (pdir / "agents" / "scribe" / "AGENT.md").write_text(
        "---\nname: scribe\ntools: file_read\n---\n\n# Role\n\n## Identity\n- plugin scribe\n",
        encoding="utf-8",
    )

    _deploy(tmp_path)

    deployed = tmp_path / ".claude" / "agents" / "scribe.md"
    assert deployed.is_file()
    assert "plugin scribe" in deployed.read_text(encoding="utf-8")


def test_user_layer_whole_file_beats_project_patch(tmp_path: Path) -> None:
    _init_project(tmp_path)
    proj = tmp_path / ".cataforge" / "overrides" / "project" / "agents" / "architect"
    proj.mkdir(parents=True)
    (proj / "AGENT.patch.md").write_text("## Identity\n- project identity\n", encoding="utf-8")
    user = tmp_path / ".cataforge" / "overrides" / "user" / "agents" / "architect"
    user.mkdir(parents=True)
    (user / "AGENT.md").write_text(
        "---\nname: architect\ntools: file_read\n---\n\n# Role\n\n## Identity\n- user identity\n",
        encoding="utf-8",
    )

    _deploy(tmp_path)

    deployed = (tmp_path / ".claude" / "agents" / "architect.md").read_text(encoding="utf-8")
    assert "user identity" in deployed
    assert "project identity" not in deployed
