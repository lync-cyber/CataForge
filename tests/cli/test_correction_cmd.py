"""Tests for ``cataforge correction record`` (interrupt-override CLI path)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.correction_cmd import record_command


def _bootstrap(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0"}), encoding="utf-8"
    )
    return tmp_path


def test_record_writes_both_logs(tmp_path: Path, monkeypatch) -> None:
    project = _bootstrap(tmp_path)
    monkeypatch.chdir(project)

    result = CliRunner().invoke(
        record_command,
        [
            "--trigger", "interrupt-override",
            "--agent", "orchestrator",
            "--phase", "architecture",
            "--question", "选 Node 版本",
            "--baseline", "B: 18 LTS",
            "--actual", "C: 22 LTS",
            "--deviation", "self-caused",
        ],
    )
    assert result.exit_code == 0, result.output

    log = project / "docs" / "reviews" / "CORRECTIONS-LOG.md"
    event_log = project / "docs" / "EVENT-LOG.jsonl"
    assert log.is_file()
    assert event_log.is_file()
    assert "interrupt-override" in log.read_text(encoding="utf-8")
    rec = json.loads(event_log.read_text(encoding="utf-8").strip())
    assert rec["event"] == "correction"


def test_record_no_event_log_flag(tmp_path: Path, monkeypatch) -> None:
    project = _bootstrap(tmp_path)
    monkeypatch.chdir(project)

    result = CliRunner().invoke(
        record_command,
        [
            "--trigger", "interrupt-override",
            "--agent", "orchestrator",
            "--phase", "x",
            "--question", "q",
            "--baseline", "b",
            "--actual", "a",
            "--no-event-log",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (project / "docs" / "reviews" / "CORRECTIONS-LOG.md").is_file()
    assert not (project / "docs" / "EVENT-LOG.jsonl").exists()


def test_record_rejects_invalid_trigger(tmp_path: Path, monkeypatch) -> None:
    project = _bootstrap(tmp_path)
    monkeypatch.chdir(project)
    result = CliRunner().invoke(
        record_command,
        [
            "--trigger", "bogus",
            "--agent", "x",
            "--phase", "x",
            "--question", "q",
            "--baseline", "b",
            "--actual", "a",
        ],
    )
    assert result.exit_code != 0
    assert "bogus" in result.output or "Invalid value" in result.output
