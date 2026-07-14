"""framework.json schema v2: deployment 分区、v1 迁移、分层解析。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.config import ConfigManager
from cataforge.core.config_migrate import (
    CONFIG_SCHEMA_VERSION,
    migrate_framework_json,
    needs_migration,
)
from cataforge.core.errors import ConfigError

V1_CONFIG = {
    "version": "0.15.0",
    "runtime_api_version": "1.0",
    "runtime": {"platform": "codex"},
    "upgrade": {
        "source": {"repo": "acme/fork", "token_env": "MY_TOKEN"},
        "state": {"event_log_validate_since": "2026-06-01T00:00:00Z"},
    },
    "constants": {"X": 1},
    "custom_block": {"user": True},
}


def _write_fw(root: Path, data: dict) -> Path:
    cataforge = root / ".cataforge"
    cataforge.mkdir(exist_ok=True)
    fw = cataforge / "framework.json"
    fw.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return fw


@pytest.fixture()
def v1_project(tmp_path: Path) -> Path:
    _write_fw(tmp_path, V1_CONFIG)
    return tmp_path


class TestNeedsMigration:
    def test_v1_detected(self, v1_project: Path) -> None:
        raw = json.loads((v1_project / ".cataforge" / "framework.json").read_text("utf-8"))
        assert needs_migration(raw) is True

    def test_v2_not_detected(self) -> None:
        assert needs_migration({"schema_version": CONFIG_SCHEMA_VERSION}) is False


class TestMigrateFrameworkJson:
    def test_platform_moves_to_deployment(self, v1_project: Path) -> None:
        result = migrate_framework_json(v1_project)
        assert result.migrated is True
        raw = json.loads((v1_project / ".cataforge" / "framework.json").read_text("utf-8"))
        assert raw["schema_version"] == CONFIG_SCHEMA_VERSION
        assert raw["deployment"]["default_platform"] == "codex"
        assert raw["deployment"]["targets"] == ["codex"]
        assert "runtime" not in raw

    def test_upgrade_state_moves_to_state_file(self, v1_project: Path) -> None:
        migrate_framework_json(v1_project)
        state_file = v1_project / ".cataforge" / "state" / "upgrade.json"
        assert state_file.is_file()
        state = json.loads(state_file.read_text("utf-8"))
        assert state["event_log_validate_since"] == "2026-06-01T00:00:00Z"
        raw = json.loads((v1_project / ".cataforge" / "framework.json").read_text("utf-8"))
        assert "state" not in raw.get("upgrade", {})
        assert raw["upgrade"]["source"]["repo"] == "acme/fork"

    def test_unknown_keys_preserved(self, v1_project: Path) -> None:
        migrate_framework_json(v1_project)
        raw = json.loads((v1_project / ".cataforge" / "framework.json").read_text("utf-8"))
        assert raw["custom_block"] == {"user": True}
        assert raw["constants"] == {"X": 1}

    def test_runtime_extra_keys_survive(self, tmp_path: Path) -> None:
        data = dict(V1_CONFIG)
        data["runtime"] = {"platform": "cursor", "user_note": "keep-me"}
        _write_fw(tmp_path, data)
        migrate_framework_json(tmp_path)
        raw = json.loads((tmp_path / ".cataforge" / "framework.json").read_text("utf-8"))
        assert raw["runtime"] == {"user_note": "keep-me"}
        assert raw["deployment"]["default_platform"] == "cursor"

    def test_idempotent_second_run_no_diff(self, v1_project: Path) -> None:
        migrate_framework_json(v1_project)
        fw = v1_project / ".cataforge" / "framework.json"
        before = fw.read_bytes()
        result = migrate_framework_json(v1_project)
        assert result.migrated is False
        assert fw.read_bytes() == before

    def test_backup_created(self, v1_project: Path) -> None:
        result = migrate_framework_json(v1_project)
        assert result.backup is not None
        assert result.backup.is_file()
        original = json.loads(result.backup.read_text("utf-8"))
        assert original["runtime"]["platform"] == "codex"

    def test_dry_run_writes_nothing(self, v1_project: Path) -> None:
        fw = v1_project / ".cataforge" / "framework.json"
        before = fw.read_bytes()
        result = migrate_framework_json(v1_project, dry_run=True)
        assert result.migrated is True
        assert fw.read_bytes() == before
        assert not (v1_project / ".cataforge" / "state" / "upgrade.json").exists()

    def test_newer_schema_rejected(self, tmp_path: Path) -> None:
        _write_fw(tmp_path, {"schema_version": CONFIG_SCHEMA_VERSION + 1})
        with pytest.raises(ConfigError):
            migrate_framework_json(tmp_path)

    def test_existing_state_file_keys_win(self, v1_project: Path) -> None:
        state_dir = v1_project / ".cataforge" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "upgrade.json").write_text(
            json.dumps({"event_log_validate_since": "newer"}), encoding="utf-8"
        )
        migrate_framework_json(v1_project)
        state = json.loads((state_dir / "upgrade.json").read_text("utf-8"))
        assert state["event_log_validate_since"] == "newer"


class TestDefaultPlatformResolution:
    def test_v2_deployment_block(self, tmp_path: Path) -> None:
        _write_fw(
            tmp_path,
            {
                "schema_version": 2,
                "deployment": {"default_platform": "opencode", "targets": ["opencode"]},
            },
        )
        assert ConfigManager(tmp_path).default_platform == "opencode"

    def test_v1_runtime_fallback(self, v1_project: Path) -> None:
        assert ConfigManager(v1_project).default_platform == "codex"

    def test_missing_defaults_to_claude_code(self, tmp_path: Path) -> None:
        _write_fw(tmp_path, {"schema_version": 2})
        assert ConfigManager(tmp_path).default_platform == "claude-code"

    def test_local_config_overrides_shared(self, tmp_path: Path) -> None:
        _write_fw(
            tmp_path,
            {"schema_version": 2, "deployment": {"default_platform": "codex"}},
        )
        (tmp_path / ".cataforge" / "config.local.json").write_text(
            json.dumps({"deployment": {"default_platform": "cursor"}}), encoding="utf-8"
        )
        assert ConfigManager(tmp_path).default_platform == "cursor"

    def test_env_overrides_local(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_fw(
            tmp_path,
            {"schema_version": 2, "deployment": {"default_platform": "codex"}},
        )
        (tmp_path / ".cataforge" / "config.local.json").write_text(
            json.dumps({"deployment": {"default_platform": "cursor"}}), encoding="utf-8"
        )
        monkeypatch.setenv("CATAFORGE_PLATFORM", "opencode")
        assert ConfigManager(tmp_path).default_platform == "opencode"

    def test_targets_declared(self, tmp_path: Path) -> None:
        _write_fw(
            tmp_path,
            {
                "schema_version": 2,
                "deployment": {
                    "default_platform": "codex",
                    "targets": ["claude-code", "codex"],
                },
            },
        )
        assert ConfigManager(tmp_path).deployment_targets == ["claude-code", "codex"]

    def test_targets_default_to_platform(self, v1_project: Path) -> None:
        assert ConfigManager(v1_project).deployment_targets == ["codex"]

    def test_explain_source_framework(self, tmp_path: Path) -> None:
        _write_fw(
            tmp_path,
            {"schema_version": 2, "deployment": {"default_platform": "codex"}},
        )
        value, source = ConfigManager(tmp_path).explain("deployment.default_platform")
        assert value == "codex"
        assert source == "framework"

    def test_explain_source_local(self, tmp_path: Path) -> None:
        _write_fw(tmp_path, {"schema_version": 2})
        (tmp_path / ".cataforge" / "config.local.json").write_text(
            json.dumps({"deployment": {"default_platform": "cursor"}}), encoding="utf-8"
        )
        value, source = ConfigManager(tmp_path).explain("deployment.default_platform")
        assert value == "cursor"
        assert source == "local"

    def test_explain_source_default(self, tmp_path: Path) -> None:
        _write_fw(tmp_path, {"schema_version": 2})
        value, source = ConfigManager(tmp_path).explain("deployment.default_platform")
        assert value == "claude-code"
        assert source == "default"

    def test_explain_source_legacy(self, v1_project: Path) -> None:
        value, source = ConfigManager(v1_project).explain("deployment.default_platform")
        assert value == "codex"
        assert source == "legacy"

    def test_explain_source_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_fw(tmp_path, {"schema_version": 2})
        monkeypatch.setenv("CATAFORGE_PLATFORM", "cursor")
        value, source = ConfigManager(tmp_path).explain("deployment.default_platform")
        assert value == "cursor"
        assert source == "env"


class TestSetDefaultPlatform:
    def test_set_writes_deployment_block(self, tmp_path: Path) -> None:
        _write_fw(tmp_path, {"schema_version": 2})
        cfg = ConfigManager(tmp_path)
        cfg.set_default_platform("codex")
        raw = json.loads((tmp_path / ".cataforge" / "framework.json").read_text("utf-8"))
        assert raw["deployment"]["default_platform"] == "codex"
        assert raw["deployment"]["targets"] == ["codex"]

    def test_set_unions_targets_never_removes(self, tmp_path: Path) -> None:
        _write_fw(
            tmp_path,
            {
                "schema_version": 2,
                "deployment": {
                    "default_platform": "claude-code",
                    "targets": ["claude-code"],
                },
            },
        )
        cfg = ConfigManager(tmp_path)
        cfg.set_default_platform("codex")
        raw = json.loads((tmp_path / ".cataforge" / "framework.json").read_text("utf-8"))
        assert raw["deployment"]["default_platform"] == "codex"
        assert raw["deployment"]["targets"] == ["claude-code", "codex"]

    def test_set_pops_legacy_runtime_platform(self, v1_project: Path) -> None:
        cfg = ConfigManager(v1_project)
        cfg.set_default_platform("cursor")
        raw = json.loads((v1_project / ".cataforge" / "framework.json").read_text("utf-8"))
        assert "runtime" not in raw
        assert raw["deployment"]["default_platform"] == "cursor"

    def test_set_same_value_no_write(self, tmp_path: Path) -> None:
        _write_fw(
            tmp_path,
            {
                "schema_version": 2,
                "deployment": {"default_platform": "codex", "targets": ["codex"]},
            },
        )
        fw = tmp_path / ".cataforge" / "framework.json"
        before_mtime = fw.stat().st_mtime_ns
        ConfigManager(tmp_path).set_default_platform("codex")
        assert fw.stat().st_mtime_ns == before_mtime

    def test_set_preserves_unknown_keys(self, v1_project: Path) -> None:
        ConfigManager(v1_project).set_default_platform("cursor")
        raw = json.loads((v1_project / ".cataforge" / "framework.json").read_text("utf-8"))
        assert raw["custom_block"] == {"user": True}
