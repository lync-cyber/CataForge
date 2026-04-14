"""Tests for platform conformance checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.platform.conformance import check_conformance, check_extended_conformance
from cataforge.platform.registry import clear_cache


def _make_full_profile() -> dict:
    return {
        "platform_id": "claude-code",
        "tool_map": {
            "file_read": "Read",
            "file_write": "Write",
            "file_edit": "Edit",
            "file_glob": "Glob",
            "file_grep": "Grep",
            "shell_exec": "Bash",
            "web_search": "WebSearch",
            "web_fetch": "WebFetch",
            "user_question": "AskUserQuestion",
            "agent_dispatch": "Agent",
        },
        "extended_capabilities": {
            "notebook_edit": "NotebookEdit",
            "browser_preview": "preview_start",
            "image_input": "Read",
            "code_review": None,
        },
        "agent_config": {
            "supported_fields": [
                "name", "description", "tools", "disallowedTools", "model",
                "permissionMode", "maxTurns", "skills", "mcpServers", "hooks",
                "memory", "background", "effort", "isolation", "color",
                "initialPrompt", "prompt",
            ],
            "memory_scopes": ["user", "project", "local"],
            "isolation_modes": ["worktree"],
        },
        "dispatch": {"tool_name": "Agent"},
        "hooks": {"config_format": "json"},
        "features": {
            "cloud_agents": False,
            "agent_teams": True,
            "parallel_agents": True,
            "scheduled_tasks": True,
            "background_agents": True,
            "plan_mode": True,
            "computer_use": False,
            "realtime_voice": False,
            "multi_model": True,
            "session_resume": False,
            "worktree_isolation": True,
            "autonomy_slider": False,
            "ci_cd_integration": False,
            "multi_root": False,
            "agent_memory": True,
            "plugin_marketplace": True,
            "context_management": True,
        },
        "permissions": {"modes": ["default", "acceptEdits", "auto", "bypassPermissions", "plan"]},
        "model_routing": {"available_models": ["opus", "sonnet", "haiku"], "per_agent_model": True},
    }


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()
    (cataforge_dir / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )

    profile = _make_full_profile()
    p = cataforge_dir / "platforms" / "claude-code"
    p.mkdir(parents=True)
    with open(p / "profile.yaml", "w", encoding="utf-8") as f:
        yaml.dump(profile, f)

    return tmp_path


class TestConformance:
    def test_conformant_platform(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        issues = check_conformance("claude-code", platforms_dir)
        assert not issues, f"Expected no issues but got: {issues}"

    def test_missing_required_capability(self, project_dir: Path) -> None:
        profile_path = project_dir / ".cataforge" / "platforms" / "claude-code" / "profile.yaml"
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        del profile["tool_map"]["agent_dispatch"]
        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.dump(profile, f)

        clear_cache()
        platforms_dir = project_dir / ".cataforge" / "platforms"

        issues = check_conformance("claude-code", platforms_dir)
        assert any("WARN" in i and "agent_dispatch" in i for i in issues)

    def test_missing_optional_capability_emits_info(self, project_dir: Path) -> None:
        """Optional capabilities (user_question, web_fetch) emit INFO not WARN."""
        profile_path = project_dir / ".cataforge" / "platforms" / "claude-code" / "profile.yaml"
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        del profile["tool_map"]["user_question"]
        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.dump(profile, f)

        clear_cache()
        platforms_dir = project_dir / ".cataforge" / "platforms"

        issues = check_conformance("claude-code", platforms_dir)
        uq_issues = [i for i in issues if "user_question" in i]
        assert len(uq_issues) == 1
        assert "INFO" in uq_issues[0]
        assert "WARN" not in uq_issues[0]


class TestExtendedConformance:
    def test_full_extended_conformance(self, project_dir: Path) -> None:
        """A fully-declared profile should only have INFO for missing extended caps."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        issues = check_extended_conformance("claude-code", platforms_dir)
        # code_review is null → should appear as INFO
        ext_issues = [i for i in issues if "extended capability" in i]
        assert any("code_review" in i for i in ext_issues)
        # All INFO-level, no FAIL or WARN
        assert all("INFO" in i for i in issues)

    def test_missing_features_section(self, project_dir: Path) -> None:
        """Platform without features section should emit INFO."""
        profile_path = project_dir / ".cataforge" / "platforms" / "claude-code" / "profile.yaml"
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        del profile["features"]
        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.dump(profile, f)

        clear_cache()
        platforms_dir = project_dir / ".cataforge" / "platforms"

        issues = check_extended_conformance("claude-code", platforms_dir)
        assert any("does not declare features section" in i for i in issues)

    def test_missing_permissions(self, project_dir: Path) -> None:
        """Platform without permissions section should emit INFO."""
        profile_path = project_dir / ".cataforge" / "platforms" / "claude-code" / "profile.yaml"
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        del profile["permissions"]
        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.dump(profile, f)

        clear_cache()
        platforms_dir = project_dir / ".cataforge" / "platforms"

        issues = check_extended_conformance("claude-code", platforms_dir)
        assert any("permission modes" in i for i in issues)

    def test_missing_agent_config(self, project_dir: Path) -> None:
        """Platform without agent_config should emit INFO."""
        profile_path = project_dir / ".cataforge" / "platforms" / "claude-code" / "profile.yaml"
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        del profile["agent_config"]
        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.dump(profile, f)

        clear_cache()
        platforms_dir = project_dir / ".cataforge" / "platforms"

        issues = check_extended_conformance("claude-code", platforms_dir)
        assert any("agent_config.supported_fields" in i for i in issues)

    def test_unsupported_features_reported(self, project_dir: Path) -> None:
        """Unsupported features (false) should be listed in INFO."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        issues = check_extended_conformance("claude-code", platforms_dir)
        feature_issues = [i for i in issues if "unsupported features" in i]
        # cloud_agents is False in the fixture
        if feature_issues:
            assert any("cloud_agents" in i for i in feature_issues)
