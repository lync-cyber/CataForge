"""Tests for cataforge.core.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.config import ConfigManager
from cataforge.core.paths import ProjectPaths


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal CataForge project structure."""
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()

    fw = {
        "version": "0.1.0",
        "runtime_api_version": "1.0",
        "runtime": {"platform": "cursor"},
        "constants": {"MAX_QUESTIONS_PER_BATCH": 3, "EVENT_LOG_PATH": "docs/EVENT-LOG.jsonl"},
        "features": {
            "tdd-engine": {"min_version": "0.1.0", "auto_enable": True},
            "penpot-bridge": {"min_version": "0.1.0", "auto_enable": False},
        },
        "upgrade": {"source": {"type": "github", "repo": "test/repo"}},
    }
    (cataforge_dir / "framework.json").write_text(json.dumps(fw), encoding="utf-8")
    return tmp_path


class TestConfigManager:
    def test_load(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        data = cfg.load()
        assert data["version"] == "0.1.0"

    def test_version(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        assert cfg.version == "0.1.0"

    def test_default_platform_legacy_fallback(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        assert cfg.default_platform == "cursor"

    def test_constants(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        assert cfg.get_constant("MAX_QUESTIONS_PER_BATCH") == 3
        assert cfg.get_constant("NONEXISTENT", "default") == "default"

    def test_features(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        assert cfg.is_feature_enabled("tdd-engine") is True
        assert cfg.is_feature_enabled("penpot-bridge") is False
        assert cfg.is_feature_enabled("nonexistent") is False

    def test_set_default_platform(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        cfg.set_default_platform("codex")
        assert cfg.default_platform == "codex"

        cfg2 = ConfigManager(project_dir)
        assert cfg2.default_platform == "codex"

    def test_languages_default_empty(self, project_dir: Path) -> None:
        assert ConfigManager(project_dir).languages == []

    def test_languages_read(self, project_dir: Path) -> None:
        fw_path = project_dir / ".cataforge" / "framework.json"
        data = json.loads(fw_path.read_text(encoding="utf-8"))
        data["project"] = {"languages": ["python", "go"]}
        fw_path.write_text(json.dumps(data), encoding="utf-8")
        assert ConfigManager(project_dir).languages == ["python", "go"]

    def test_set_languages_preserves_other_fields(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        cfg.set_languages(["python"])
        assert cfg.languages == ["python"]
        # Unrelated fields untouched.
        reread = ConfigManager(project_dir)
        assert reread.default_platform == "cursor"
        assert reread.get_constant("MAX_QUESTIONS_PER_BATCH") == 3
        assert reread.languages == ["python"]

    def test_set_languages_survives_platform_change(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        cfg.set_languages(["rust", "go"])
        cfg.set_default_platform("codex")
        reread = ConfigManager(project_dir)
        assert reread.languages == ["rust", "go"]
        assert reread.default_platform == "codex"

    def test_reload(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        assert cfg.version == "0.1.0"

        fw_path = project_dir / ".cataforge" / "framework.json"
        data = json.loads(fw_path.read_text(encoding="utf-8"))
        data["version"] = "0.5.0"
        fw_path.write_text(json.dumps(data), encoding="utf-8")

        assert cfg.version == "0.1.0"  # cached
        cfg.reload()
        assert cfg.version == "0.5.0"

    def test_missing_framework_json(self, tmp_path: Path) -> None:
        (tmp_path / ".cataforge").mkdir()
        cfg = ConfigManager(tmp_path)
        assert cfg.load() == {}
        assert cfg.version == "0.0.0"

    def test_claude_md_limits_defaults(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        limits = cfg.claude_md_limits
        assert limits["max_bytes"] == 30000
        assert limits["max_state_section_lines"] == 80
        assert limits["learnings_registry_max_entries"] == 10

    def test_claude_md_limits_overrides(self, project_dir: Path) -> None:
        fw_path = project_dir / ".cataforge" / "framework.json"
        data = json.loads(fw_path.read_text(encoding="utf-8"))
        data["claude_md_limits"] = {"max_bytes": 50000}
        fw_path.write_text(json.dumps(data), encoding="utf-8")
        cfg = ConfigManager(project_dir)
        limits = cfg.claude_md_limits
        assert limits["max_bytes"] == 50000
        assert limits["max_state_section_lines"] == 80

    def test_claude_md_limits_invalid_string_raises(self, project_dir: Path) -> None:
        fw_path = project_dir / ".cataforge" / "framework.json"
        data = json.loads(fw_path.read_text(encoding="utf-8"))
        data["claude_md_limits"] = {"max_bytes": "unlimited"}
        fw_path.write_text(json.dumps(data), encoding="utf-8")
        cfg = ConfigManager(project_dir)
        with pytest.raises(ValueError, match="claude_md_limits.max_bytes"):
            _ = cfg.claude_md_limits


class TestGitSessionSync:
    def test_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".cataforge").mkdir()
        (tmp_path / ".cataforge" / "framework.json").write_text(
            json.dumps({"version": "0.1.0"}), encoding="utf-8"
        )
        ss = ConfigManager(tmp_path).git_session_sync
        assert ss.enabled is True
        assert ss.fast_forward_clean is True
        assert ss.prune_gone is True
        assert ss.confirm_via_gh is True
        assert ss.debounce_seconds == 60
        assert ss.fetch_timeout_seconds == 10

    def test_reads_overrides(self, project_dir: Path) -> None:
        fw_path = project_dir / ".cataforge" / "framework.json"
        data = json.loads(fw_path.read_text(encoding="utf-8"))
        data["git"] = {"session_sync": {"enabled": False, "fetch_timeout_seconds": 5}}
        fw_path.write_text(json.dumps(data), encoding="utf-8")
        ss = ConfigManager(project_dir).git_session_sync
        assert ss.enabled is False
        assert ss.fetch_timeout_seconds == 5
        # unset sub-fields still fall back to their defaults
        assert ss.prune_gone is True

    def test_git_section_survives_platform_write(self, project_dir: Path) -> None:
        fw_path = project_dir / ".cataforge" / "framework.json"
        data = json.loads(fw_path.read_text(encoding="utf-8"))
        data["git"] = {"session_sync": {"enabled": False}}
        data["my_custom_key"] = {"keep": 1}
        fw_path.write_text(json.dumps(data), encoding="utf-8")

        cfg = ConfigManager(project_dir)
        cfg.set_default_platform("codex")

        reread = ConfigManager(project_dir)
        assert reread.git_session_sync.enabled is False
        assert reread.default_platform == "codex"
        # The verbatim writer must not drop an unknown top-level key.
        assert reread.load_raw()["my_custom_key"] == {"keep": 1}


class TestProjectPaths:
    def test_paths_from_root(self, project_dir: Path) -> None:
        paths = ProjectPaths(project_dir)
        assert paths.cataforge_dir == project_dir / ".cataforge"
        assert paths.framework_json == project_dir / ".cataforge" / "framework.json"
        assert paths.agents_dir == project_dir / ".cataforge" / "agents"
        assert paths.skills_dir == project_dir / ".cataforge" / "skills"
        assert paths.hooks_spec == project_dir / ".cataforge" / "hooks" / "hooks.yaml"
        assert paths.mcp_dir == project_dir / ".cataforge" / "mcp"
        assert paths.git_sync_stamp == project_dir / ".cataforge" / ".git-sync-stamp"

    def test_platform_profile(self, project_dir: Path) -> None:
        paths = ProjectPaths(project_dir)
        assert paths.platform_profile("cursor") == (
            project_dir / ".cataforge" / "platforms" / "cursor" / "profile.yaml"
        )
