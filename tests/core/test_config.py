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
            "penpot-sync": {"min_version": "0.1.0", "auto_enable": False},
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

    def test_runtime_platform(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        assert cfg.runtime_platform == "cursor"

    def test_constants(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        assert cfg.get_constant("MAX_QUESTIONS_PER_BATCH") == 3
        assert cfg.get_constant("NONEXISTENT", "default") == "default"

    def test_features(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        assert cfg.is_feature_enabled("tdd-engine") is True
        assert cfg.is_feature_enabled("penpot-sync") is False
        assert cfg.is_feature_enabled("nonexistent") is False

    def test_set_runtime_platform(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        cfg.set_runtime_platform("codex")
        assert cfg.runtime_platform == "codex"

        cfg2 = ConfigManager(project_dir)
        assert cfg2.runtime_platform == "codex"

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
        assert reread.runtime_platform == "cursor"
        assert reread.get_constant("MAX_QUESTIONS_PER_BATCH") == 3
        assert reread.languages == ["python"]

    def test_set_languages_survives_platform_change(self, project_dir: Path) -> None:
        cfg = ConfigManager(project_dir)
        cfg.set_languages(["rust", "go"])
        cfg.set_runtime_platform("codex")
        reread = ConfigManager(project_dir)
        assert reread.languages == ["rust", "go"]
        assert reread.runtime_platform == "codex"

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


class TestProjectPaths:
    def test_paths_from_root(self, project_dir: Path) -> None:
        paths = ProjectPaths(project_dir)
        assert paths.cataforge_dir == project_dir / ".cataforge"
        assert paths.framework_json == project_dir / ".cataforge" / "framework.json"
        assert paths.agents_dir == project_dir / ".cataforge" / "agents"
        assert paths.skills_dir == project_dir / ".cataforge" / "skills"
        assert paths.hooks_spec == project_dir / ".cataforge" / "hooks" / "hooks.yaml"
        assert paths.mcp_dir == project_dir / ".cataforge" / "mcp"

    def test_platform_profile(self, project_dir: Path) -> None:
        paths = ProjectPaths(project_dir)
        assert paths.platform_profile("cursor") == (
            project_dir / ".cataforge" / "platforms" / "cursor" / "profile.yaml"
        )
