"""测试 deploy 端到端逻辑。"""
import pytest
from pathlib import Path
from runtime.deploy import get_project_root, deploy
from runtime.profile_loader import load_profile


class TestGetProjectRoot:
    def test_returns_valid_path(self):
        root = get_project_root()
        assert root.is_dir()
        assert (root / ".cataforge").is_dir()


class TestDeploy:
    def test_claude_code_deploy_returns_actions(self):
        actions = deploy("claude-code")
        assert len(actions) > 0
        agent_actions = [a for a in actions if "agents/" in a]
        assert len(agent_actions) > 0

    def test_claude_code_generates_claude_md(self):
        root = get_project_root()
        deploy("claude-code")
        claude_md = root / "CLAUDE.md"
        assert claude_md.is_file()
        content = claude_md.read_text(encoding="utf-8")
        assert "运行时: claude-code" in content

    def test_deploy_state_written(self):
        root = get_project_root()
        deploy("claude-code")
        state_file = root / ".cataforge" / ".deploy-state"
        assert state_file.is_file()

    def test_cursor_deploy_returns_actions(self):
        actions = deploy("cursor")
        assert len(actions) > 0


class TestDeployConformance:
    def test_all_profiles_loadable(self):
        for pid in ["claude-code", "cursor", "codex", "opencode"]:
            profile = load_profile(pid)
            assert profile["platform_id"] == pid
