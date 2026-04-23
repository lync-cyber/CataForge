"""Smoke tests for `cataforge event log` (single + batch)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.core.event_log import EVENT_LOG_REL


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal project (just the `.cataforge/` marker) so path discovery resolves."""
    (tmp_path / ".cataforge").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _invoke(*args: str, input: str | None = None) -> "object":
    runner = CliRunner()
    return runner.invoke(cli, list(args), input=input, catch_exceptions=False)


class TestEventLogSingle:
    def test_writes_jsonl(self, project: Path) -> None:
        result = _invoke(
            "event", "log",
            "--event", "phase_start",
            "--phase", "architecture",
            "--detail", "进入架构设计阶段",
        )
        assert result.exit_code == 0, result.output

        log = project / EVENT_LOG_REL
        line = log.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["event"] == "phase_start"
        assert record["phase"] == "architecture"
        assert record["detail"] == "进入架构设计阶段"
        assert "ts" in record

    def test_missing_required_option_errors(self, project: Path) -> None:
        result = _invoke(
            "event", "log", "--event", "phase_start", "--detail", "x"
        )
        assert result.exit_code != 0
        assert "required" in result.output.lower()

    def test_rejects_unknown_event(self, project: Path) -> None:
        result = _invoke(
            "event", "log",
            "--event", "framework:setup",  # not in schema enum
            "--phase", "x",
            "--detail", "y",
        )
        assert result.exit_code != 0
        assert "not in enum" in result.output

    def test_data_merges_with_flags(self, project: Path) -> None:
        # --data can supply optional fields not exposed as flags.
        result = _invoke(
            "event", "log",
            "--event", "agent_dispatch",
            "--phase", "development",
            "--detail", "dispatching architect",
            "--data", '{"agent":"architect","task_type":"new_creation"}',
        )
        assert result.exit_code == 0, result.output
        record = json.loads(
            (project / EVENT_LOG_REL).read_text(encoding="utf-8").strip()
        )
        assert record["agent"] == "architect"
        assert record["task_type"] == "new_creation"


class TestEventLogBatch:
    def test_atomic_all_or_nothing(self, project: Path) -> None:
        payload = (
            '{"event":"phase_end","phase":"dev_planning","status":"approved","detail":"ok"}\n'
            '{"event":"NOT_VALID","phase":"x","detail":"bad"}\n'
        )
        result = _invoke("event", "log", "--batch", input=payload)
        assert result.exit_code != 0
        # Not even the first (valid) record lands.
        assert not (project / EVENT_LOG_REL).exists()

    def test_writes_all_records(self, project: Path) -> None:
        payload = (
            '{"event":"phase_end","phase":"dev_planning","status":"approved","detail":"a"}\n'
            '{"event":"review_verdict","phase":"dev_planning","agent":"reviewer","status":"approved","detail":"b"}\n'
            '{"event":"state_change","phase":"development","detail":"c"}\n'
            '{"event":"phase_start","phase":"development","detail":"d"}\n'
        )
        result = _invoke("event", "log", "--batch", input=payload)
        assert result.exit_code == 0, result.output

        lines = (project / EVENT_LOG_REL).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 4
        assert [json.loads(line)["event"] for line in lines] == [
            "phase_end", "review_verdict", "state_change", "phase_start",
        ]

    def test_batch_mutex_with_single_flags(self, project: Path) -> None:
        result = _invoke(
            "event", "log",
            "--batch",
            "--event", "phase_start",
            input='{"event":"x","phase":"y","detail":"z"}\n',
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_batch_empty_stdin_errors(self, project: Path) -> None:
        result = _invoke("event", "log", "--batch", input="")
        assert result.exit_code != 0
        assert "empty" in result.output.lower()
