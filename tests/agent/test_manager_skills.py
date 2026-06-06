"""AgentManager.skills_for + ``cataforge agent list --skills``."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.main import cli
from cataforge.runtime.agent.manager import AgentManager


def _write_agent(tmp_path: Path, agent_id: str, frontmatter_body: str) -> None:
    agents_dir = tmp_path / ".cataforge" / "agents" / agent_id
    agents_dir.mkdir(parents=True)
    (agents_dir / "AGENT.md").write_text(frontmatter_body, encoding="utf-8")


class TestSkillsFor:
    def test_block_style_skills(self, tmp_path: Path) -> None:
        body = "---\nname: a1\nskills:\n  - req-analysis\n  - context\n---\nBody\n"
        _write_agent(tmp_path, "a1", body)
        assert AgentManager(project_root=tmp_path).skills_for("a1") == ["req-analysis", "context"]

    def test_flow_style_skills(self, tmp_path: Path) -> None:
        _write_agent(tmp_path, "a2", "---\nname: a2\nskills: [arc-design, context]\n---\nBody\n")
        assert AgentManager(project_root=tmp_path).skills_for("a2") == ["arc-design", "context"]

    def test_empty_skills_returns_empty_list(self, tmp_path: Path) -> None:
        _write_agent(tmp_path, "a3", "---\nname: a3\nskills: []  # dispatched inline\n---\nBody\n")
        assert AgentManager(project_root=tmp_path).skills_for("a3") == []

    def test_missing_skills_key_returns_empty_list(self, tmp_path: Path) -> None:
        _write_agent(tmp_path, "a4", "---\nname: a4\n---\nBody\n")
        assert AgentManager(project_root=tmp_path).skills_for("a4") == []

    def test_missing_agent_returns_empty_list(self, tmp_path: Path) -> None:
        (tmp_path / ".cataforge" / "agents").mkdir(parents=True)
        assert AgentManager(project_root=tmp_path).skills_for("ghost") == []


class TestAgentListSkillsFlag:
    @pytest.fixture
    def fresh_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        from cataforge.core.scaffold import copy_scaffold_to

        copy_scaffold_to(tmp_path / ".cataforge", force=False)
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_list_skills_shows_mapping(self, fresh_project: Path) -> None:
        result = CliRunner().invoke(cli, ["agent", "list", "--skills"], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        assert "architect" in result.output
        assert "arc-design" in result.output

    def test_list_without_flag_omits_skills(self, fresh_project: Path) -> None:
        result = CliRunner().invoke(cli, ["agent", "list"], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        assert "architect" in result.output
        assert "arc-design" not in result.output
