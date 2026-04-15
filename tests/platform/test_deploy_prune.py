"""Tests for deploy prune behavior (commands + agents orphan cleanup)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cataforge.platform.base import PlatformAdapter


class _MinimalAdapter(PlatformAdapter):
    """Test adapter exercising default deploy_commands / deploy_agents."""

    def __init__(self, profile: dict[str, Any]) -> None:
        super().__init__(profile)

    @property
    def platform_id(self) -> str:
        return "test"

    @property
    def display_name(self) -> str:
        return "Test"

    def get_tool_map(self) -> dict[str, str | None]:
        return {}

    def get_project_root_env_var(self) -> str | None:
        return None

    def get_agent_scan_dirs(self) -> list[str]:
        return [".test/agents"]

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    def inject_mcp_config(self, server_id, server_config, project_root, *, dry_run=False):
        return []


@pytest.fixture()
def adapter() -> _MinimalAdapter:
    return _MinimalAdapter(
        {
            "command_definition": {
                "needs_deploy": True,
                "target_dir": ".test/commands",
            },
            "agent_definition": {
                "needs_deploy": True,
                "scan_dirs": [".test/agents"],
            },
        }
    )


def test_deploy_commands_prunes_orphans(tmp_path: Path, adapter: _MinimalAdapter) -> None:
    source = tmp_path / ".cataforge" / "commands"
    source.mkdir(parents=True)
    (source / "bootstrap.md").write_text("new\n", encoding="utf-8")

    # Pre-seed an orphan from a "previous deploy".
    target = tmp_path / ".test" / "commands"
    target.mkdir(parents=True)
    (target / "legacy.md").write_text("stale\n", encoding="utf-8")

    actions = adapter.deploy_commands(source, tmp_path)
    assert (target / "bootstrap.md").is_file()
    assert not (target / "legacy.md").exists()
    assert any("pruned orphan" in a and "legacy.md" in a for a in actions)


def test_deploy_commands_leaves_foreign_non_md_alone(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    source = tmp_path / ".cataforge" / "commands"
    source.mkdir(parents=True)
    (source / "bootstrap.md").write_text("new\n", encoding="utf-8")

    target = tmp_path / ".test" / "commands"
    target.mkdir(parents=True)
    (target / "README.txt").write_text("keep me\n", encoding="utf-8")

    adapter.deploy_commands(source, tmp_path)
    assert (target / "README.txt").is_file()


def test_deploy_agents_prunes_orphan_subdirs(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    source = tmp_path / ".cataforge" / "agents"
    (source / "orchestrator").mkdir(parents=True)
    (source / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\n---\nbody\n", encoding="utf-8"
    )

    # Pre-seed an orphan agent dir that would have been deployed by a prior run.
    target = tmp_path / ".test" / "agents"
    orphan = target / "retired-agent"
    orphan.mkdir(parents=True)
    (orphan / "AGENT.md").write_text(
        "---\nname: retired-agent\n---\nold\n", encoding="utf-8"
    )

    adapter.deploy_agents(source, tmp_path)
    assert (target / "orchestrator" / "AGENT.md").is_file()
    assert not orphan.exists()


def test_deploy_agents_prunes_sibling_reference_files(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    source = tmp_path / ".cataforge" / "agents"
    (source / "orchestrator").mkdir(parents=True)
    (source / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\n---\nbody\n", encoding="utf-8"
    )

    # Previous deploy left a sibling file (e.g. ORCHESTRATOR-PROTOCOLS.md).
    target = tmp_path / ".test" / "agents" / "orchestrator"
    target.mkdir(parents=True)
    (target / "ORCHESTRATOR-PROTOCOLS.md").write_text("stale\n", encoding="utf-8")

    adapter.deploy_agents(source, tmp_path)
    assert (target / "AGENT.md").is_file()
    assert not (target / "ORCHESTRATOR-PROTOCOLS.md").exists()


def test_deploy_agents_does_not_prune_native_agents(
    tmp_path: Path, adapter: _MinimalAdapter
) -> None:
    """Dirs without AGENT.md (IDE-native / user-authored) must survive."""
    source = tmp_path / ".cataforge" / "agents"
    (source / "orchestrator").mkdir(parents=True)
    (source / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\n---\nbody\n", encoding="utf-8"
    )

    target = tmp_path / ".test" / "agents"
    native = target / "native-agent"
    native.mkdir(parents=True)
    (native / "config.yaml").write_text("native: true\n", encoding="utf-8")

    adapter.deploy_agents(source, tmp_path)
    assert native.is_dir()
    assert (native / "config.yaml").is_file()
