"""Regression: doctor must exit non-zero when migration checks fail."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.doctor_cmd import doctor_command


def _minimal_project(tmp_path: Path, checks: list[dict]) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "migration_checks": checks}),
        encoding="utf-8",
    )
    return tmp_path


def test_doctor_passes_with_no_checks(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path, [])
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0


def test_doctor_fails_when_migration_check_fails(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(
        tmp_path,
        [
            {
                "id": "test-must-exist",
                "type": "file_must_exist",
                "path": "nonexistent.md",
            }
        ],
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1
    assert "FAIL test-must-exist" in result.output


def test_doctor_passes_when_checks_satisfied(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(
        tmp_path,
        [
            {
                "id": "test-must-exist",
                "type": "file_must_exist",
                "path": ".cataforge/framework.json",
            }
        ],
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0
