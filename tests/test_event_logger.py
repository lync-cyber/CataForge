"""event_logger.py append_event function tests"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts"))
from event_logger import VALID_EVENTS, VALID_STATUSES, VALID_TASK_TYPES, append_event


class TestAppendEvent:
    def test_writes_basic_event(self, tmp_path):
        log = tmp_path / "events.jsonl"
        entry = append_event(
            event="session_start",
            phase="architecture",
            detail="会话启动",
            log_path=str(log),
        )
        assert entry["event"] == "session_start"
        assert entry["phase"] == "architecture"
        assert entry["detail"] == "会话启动"
        assert "ts" in entry

        lines = log.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["event"] == "session_start"

    def test_writes_all_optional_fields(self, tmp_path):
        log = tmp_path / "events.jsonl"
        entry = append_event(
            event="agent_dispatch",
            phase="development",
            detail="调度 architect",
            agent="architect",
            task_type="new_creation",
            status="completed",
            ref="docs/arch.md",
            log_path=str(log),
        )
        assert entry["agent"] == "architect"
        assert entry["task_type"] == "new_creation"
        assert entry["status"] == "completed"
        assert entry["ref"] == "docs/arch.md"

    def test_omits_none_optional_fields(self, tmp_path):
        log = tmp_path / "events.jsonl"
        entry = append_event(
            event="phase_start",
            phase="testing",
            detail="开始测试",
            log_path=str(log),
        )
        assert "agent" not in entry
        assert "task_type" not in entry
        assert "status" not in entry
        assert "ref" not in entry

    def test_appends_multiple_events(self, tmp_path):
        log = tmp_path / "events.jsonl"
        append_event(event="phase_start", phase="dev", detail="1", log_path=str(log))
        append_event(event="phase_end", phase="dev", detail="2", log_path=str(log))
        lines = log.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_creates_parent_directory(self, tmp_path):
        log = tmp_path / "sub" / "dir" / "events.jsonl"
        append_event(
            event="session_start",
            phase="unknown",
            detail="test",
            log_path=str(log),
        )
        assert log.exists()

    def test_invalid_event_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid event"):
            append_event(
                event="nonexistent",
                phase="dev",
                detail="x",
                log_path=str(tmp_path / "e.jsonl"),
            )

    def test_invalid_status_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid status"):
            append_event(
                event="agent_return",
                phase="dev",
                detail="x",
                status="bad_status",
                log_path=str(tmp_path / "e.jsonl"),
            )

    def test_invalid_task_type_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid task_type"):
            append_event(
                event="agent_dispatch",
                phase="dev",
                detail="x",
                task_type="invalid",
                log_path=str(tmp_path / "e.jsonl"),
            )


class TestValidSets:
    def test_all_13_events(self):
        assert len(VALID_EVENTS) == 13

    def test_all_7_statuses(self):
        assert len(VALID_STATUSES) == 7

    def test_expected_events_present(self):
        expected = {
            "session_start",
            "phase_start",
            "phase_end",
            "agent_dispatch",
            "agent_return",
            "review_verdict",
            "user_decision",
            "revision_start",
            "tdd_phase",
            "incident",
            "state_change",
            "correction",
            "doc_finalize",
        }
        assert VALID_EVENTS == expected
