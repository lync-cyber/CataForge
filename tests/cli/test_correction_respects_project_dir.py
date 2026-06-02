"""Verify that ``--project-dir`` propagates into ``correction record``."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.interface.cli.main import cli


def _bootstrap(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0"}), encoding="utf-8"
    )
    return tmp_path


def test_record_writes_to_project_dir(tmp_path: Path, monkeypatch) -> None:
    tmp_root = _bootstrap(tmp_path / "project")
    cwd = tmp_path / "other"
    cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd)

    result = CliRunner().invoke(
        cli,
        [
            "--project-dir",
            str(tmp_root),
            "correction",
            "record",
            "--trigger",
            "option-override",
            "--agent",
            "orchestrator",
            "--phase",
            "implementation",
            "--question",
            "q",
            "--baseline",
            "b",
            "--actual",
            "a",
        ],
    )
    assert result.exit_code == 0, result.output

    log = tmp_root / "docs" / "reviews" / "CORRECTIONS-LOG.md"
    assert log.is_file(), "CORRECTIONS-LOG.md must be written under --project-dir"
    assert "option-override" in log.read_text(encoding="utf-8")

    wrong = cwd / "docs" / "reviews" / "CORRECTIONS-LOG.md"
    assert not wrong.exists(), "must not write under cwd when --project-dir is set"
