"""Tests for platform conformance checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.adapter.platform.conformance import (
    _load_hook_degradation_strategies,
    check_all_consistency,
    check_conformance,
    check_extended_conformance,
    check_platform_consistency,
)
from cataforge.adapter.platform.registry import clear_cache

REPO_PLATFORMS_DIR = Path(__file__).resolve().parents[2] / ".cataforge" / "platforms"


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
                "name",
                "description",
                "tools",
                "disallowedTools",
                "model",
                "permissionMode",
                "maxTurns",
                "skills",
                "mcpServers",
                "hooks",
                "memory",
                "background",
                "effort",
                "isolation",
                "color",
                "initialPrompt",
                "prompt",
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
        # cloud_agents is False in the fixture — must always produce a report
        assert feature_issues, "expected unsupported-features INFO line but got none"
        assert any("cloud_agents" in i for i in feature_issues)


def _rewrite_profile(project_dir: Path, mutate) -> Path:
    profile_path = project_dir / ".cataforge" / "platforms" / "claude-code" / "profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    mutate(profile)
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(profile, f)
    clear_cache()
    return project_dir / ".cataforge" / "platforms"


class TestPlatformConsistency:
    def test_clean_profile_has_no_consistency_warn(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        issues = check_platform_consistency("claude-code", platforms_dir)
        assert issues == [], f"expected clean profile but got: {issues}"

    def test_web_fetch_routed_to_shell_warns(self, project_dir: Path) -> None:
        def mutate(p: dict) -> None:
            p["tool_map"]["web_fetch"] = p["tool_map"]["shell_exec"]

        platforms_dir = _rewrite_profile(project_dir, mutate)
        issues = check_platform_consistency("claude-code", platforms_dir)
        assert any("WARN" in i and "web_fetch" in i and "shell" in i for i in issues)

    def test_computer_use_without_browser_preview_warns(self, project_dir: Path) -> None:
        def mutate(p: dict) -> None:
            p["features"]["computer_use"] = True
            p["extended_capabilities"]["browser_preview"] = None

        platforms_dir = _rewrite_profile(project_dir, mutate)
        issues = check_platform_consistency("claude-code", platforms_dir)
        assert any("WARN" in i and "computer_use" in i and "browser_preview" in i for i in issues)

    def test_worktree_isolation_without_field_warns(self, project_dir: Path) -> None:
        def mutate(p: dict) -> None:
            p["features"]["worktree_isolation"] = True
            p["agent_config"]["supported_fields"] = [
                f for f in p["agent_config"]["supported_fields"] if f != "isolation"
            ]

        platforms_dir = _rewrite_profile(project_dir, mutate)
        issues = check_platform_consistency("claude-code", platforms_dir)
        assert any("WARN" in i and "worktree_isolation" in i and "isolation" in i for i in issues)

    def test_nonconventional_scan_dir_warns(self, project_dir: Path) -> None:
        def mutate(p: dict) -> None:
            p["agent_definition"] = {"scan_dirs": [".cursor/agents/custom"]}

        platforms_dir = _rewrite_profile(project_dir, mutate)
        issues = check_platform_consistency("claude-code", platforms_dir)
        assert any("WARN" in i and "scan dir" in i and "rules" in i for i in issues)

    def test_conventional_scan_dir_clean(self, project_dir: Path) -> None:
        def mutate(p: dict) -> None:
            p["agent_definition"] = {"scan_dirs": [".claude/agents"]}

        platforms_dir = _rewrite_profile(project_dir, mutate)
        issues = check_platform_consistency("claude-code", platforms_dir)
        assert not any("scan dir" in i for i in issues)

    def test_hook_strategies_none_when_hooks_yaml_absent(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        assert _load_hook_degradation_strategies(platforms_dir) is None


class TestConsistencySnapshot:
    """Snapshot the WARN set the real four profiles produce today.

    These four are the report-02 deferred findings the guard is built to keep
    visible. The snapshot breaks (deliberately) if a profile is changed to
    resolve or introduce one — at which point the expected set is updated.
    """

    def test_expected_warn_set(self) -> None:
        lines = check_all_consistency(REPO_PLATFORMS_DIR)
        blob = "\n".join(lines)
        # No profile should fail to load.
        assert "FAIL" not in blob, blob
        # codex H-3: web_fetch routed to shell
        assert any("codex" in ln and "web_fetch" in ln for ln in lines)
        # codex M-5: computer_use feature without browser_preview mapping
        assert any("codex" in ln and "browser_preview" in ln for ln in lines)
        # cursor L-4: worktree_isolation without the isolation field
        assert any("cursor" in ln and "worktree_isolation" in ln for ln in lines)
        # notify_permission is native on claude-code AND codex — no lone-native
        # outlier WARN for it.
        assert not any("notify_permission" in ln for ln in lines)
