"""cataforge config 子命令：validate / get / set / explain / migrate。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.cli.conftest import make_minimal_project


def _run(args: list[str], root: Path, monkeypatch: pytest.MonkeyPatch):
    from cataforge.interface.cli.main import cli

    monkeypatch.chdir(root)
    return CliRunner().invoke(cli, args)


def _fw_path(root: Path) -> Path:
    return root / ".cataforge" / "framework.json"


def _patch_fw(root: Path, patch: dict) -> None:
    fw = _fw_path(root)
    data = json.loads(fw.read_text("utf-8"))
    data.update(patch)
    fw.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestConfigValidate:
    def test_valid_v2_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(
            root,
            {"schema_version": 2, "deployment": {"default_platform": "claude-code"}},
        )
        result = _run(["config", "validate"], root, monkeypatch)
        assert result.exit_code == 0, result.output

    def test_v1_reports_migration_needed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"runtime": {"platform": "codex"}})
        result = _run(["config", "validate"], root, monkeypatch)
        assert "config migrate" in result.output

    def test_newer_schema_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 99})
        result = _run(["config", "validate"], root, monkeypatch)
        assert result.exit_code != 0

    def test_invalid_platform_in_targets_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(
            root,
            {"schema_version": 2, "deployment": {"targets": ["not-a-platform"]}},
        )
        result = _run(["config", "validate"], root, monkeypatch)
        assert result.exit_code != 0
        assert "not-a-platform" in result.output


class TestConfigGetExplain:
    def test_get_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(
            root,
            {"schema_version": 2, "deployment": {"default_platform": "codex"}},
        )
        result = _run(["config", "get", "deployment.default_platform"], root, monkeypatch)
        assert result.exit_code == 0
        assert "codex" in result.output

    def test_explain_shows_source(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(
            root,
            {"schema_version": 2, "deployment": {"default_platform": "codex"}},
        )
        result = _run(["config", "explain", "deployment.default_platform"], root, monkeypatch)
        assert result.exit_code == 0
        assert "codex" in result.output
        assert "framework" in result.output

    def test_explain_default_source(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 2})
        result = _run(["config", "explain", "deployment.default_platform"], root, monkeypatch)
        assert "default" in result.output


class TestConfigSet:
    def test_set_default_platform(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 2})
        result = _run(["config", "set", "deployment.default_platform", "codex"], root, monkeypatch)
        assert result.exit_code == 0, result.output
        raw = json.loads(_fw_path(root).read_text("utf-8"))
        assert raw["deployment"]["default_platform"] == "codex"

    def test_set_targets_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 2})
        result = _run(
            ["config", "set", "deployment.targets", "claude-code,codex"], root, monkeypatch
        )
        assert result.exit_code == 0, result.output
        raw = json.loads(_fw_path(root).read_text("utf-8"))
        assert raw["deployment"]["targets"] == ["claude-code", "codex"]

    def test_set_same_value_no_file_change(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(
            root,
            {"schema_version": 2, "deployment": {"default_platform": "codex"}},
        )
        before = _fw_path(root).stat().st_mtime_ns
        result = _run(["config", "set", "deployment.default_platform", "codex"], root, monkeypatch)
        assert result.exit_code == 0
        assert _fw_path(root).stat().st_mtime_ns == before

    def test_set_dry_run_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 2})
        before = _fw_path(root).read_bytes()
        result = _run(
            ["config", "set", "deployment.default_platform", "codex", "--dry-run"],
            root,
            monkeypatch,
        )
        assert result.exit_code == 0
        assert _fw_path(root).read_bytes() == before

    def test_set_project_languages_normalizes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 2})
        result = _run(
            ["config", "set", "project.languages", "TypeScript, python"], root, monkeypatch
        )
        assert result.exit_code == 0, result.output
        raw = json.loads(_fw_path(root).read_text("utf-8"))
        assert raw["project"]["languages"] == ["js-ts", "python"]

    def test_set_project_languages_empty_reenables_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 2, "project": {"languages": ["python"]}})
        result = _run(["config", "set", "project.languages", ""], root, monkeypatch)
        assert result.exit_code == 0, result.output
        raw = json.loads(_fw_path(root).read_text("utf-8"))
        assert raw["project"]["languages"] == []

    def test_set_non_whitelisted_path_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 2})
        result = _run(["config", "set", "constants.X", "1"], root, monkeypatch)
        assert result.exit_code != 0

    def test_set_invalid_platform_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"schema_version": 2})
        result = _run(["config", "set", "deployment.default_platform", "vim"], root, monkeypatch)
        assert result.exit_code != 0


class TestConfigMigrate:
    def test_migrate_v1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(
            root,
            {
                "runtime": {"platform": "codex"},
                "upgrade": {"state": {"event_log_validate_since": "w"}},
            },
        )
        result = _run(["config", "migrate"], root, monkeypatch)
        assert result.exit_code == 0, result.output
        raw = json.loads(_fw_path(root).read_text("utf-8"))
        assert raw["schema_version"] == 2
        assert raw["deployment"]["default_platform"] == "codex"
        assert (root / ".cataforge" / "state" / "upgrade.json").is_file()

    def test_migrate_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = make_minimal_project(tmp_path)
        _patch_fw(root, {"runtime": {"platform": "codex"}})
        _run(["config", "migrate"], root, monkeypatch)
        before = _fw_path(root).read_bytes()
        result = _run(["config", "migrate"], root, monkeypatch)
        assert result.exit_code == 0
        assert _fw_path(root).read_bytes() == before
