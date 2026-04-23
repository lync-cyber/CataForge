"""Tests for cataforge.core.event_log — the durable JSONL writer.

These cover the two things that would silently corrupt the log otherwise:
schema enforcement (bad enum values, missing required fields, unknown keys)
and batch atomicity (one bad record rejects the whole batch).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.event_log import (
    EVENT_LOG_REL,
    EventLogError,
    append_batch,
    append_event,
    build_record,
    parse_batch_stream,
    validate_record,
)


class TestValidateRecord:
    def test_minimal_valid(self) -> None:
        errors = validate_record({
            "ts": "2026-04-23T12:00:00+00:00",
            "event": "phase_start",
            "phase": "architecture",
            "detail": "hi",
        })
        assert errors == []

    def test_missing_required(self) -> None:
        errors = validate_record({"event": "phase_start"})
        assert any("missing required field: 'ts'" in e for e in errors)
        assert any("'phase'" in e for e in errors)
        assert any("'detail'" in e for e in errors)

    def test_unknown_event_enum(self) -> None:
        errors = validate_record({
            "ts": "2026-04-23T12:00:00+00:00",
            "event": "framework:setup",  # colon-style, not in schema enum
            "phase": "x",
            "detail": "y",
        })
        assert any("event=" in e and "not in enum" in e for e in errors)

    def test_unknown_top_level_field(self) -> None:
        errors = validate_record({
            "ts": "2026-04-23T12:00:00+00:00",
            "event": "phase_start",
            "phase": "x",
            "detail": "y",
            "data": {"blob": True},  # legacy EventBus field
        })
        assert any("unknown field" in e for e in errors)

    def test_bad_status_enum(self) -> None:
        errors = validate_record({
            "ts": "2026-04-23T12:00:00+00:00",
            "event": "review_verdict",
            "phase": "x",
            "detail": "y",
            "status": "OK",  # not in enum
        })
        assert any("status=" in e for e in errors)

    def test_non_string_field(self) -> None:
        errors = validate_record({
            "ts": "2026-04-23T12:00:00+00:00",
            "event": "phase_start",
            "phase": 42,  # not a string
            "detail": "y",
        })
        assert any("'phase' must be a string" in e for e in errors)


class TestBuildRecord:
    def test_auto_timestamp(self) -> None:
        rec = build_record(
            event="phase_start", phase="architecture", detail="进入架构"
        )
        assert rec["ts"].endswith("+00:00")
        assert rec["event"] == "phase_start"

    def test_optional_fields_omitted_when_none(self) -> None:
        rec = build_record(event="phase_start", phase="x", detail="y")
        assert "agent" not in rec
        assert "status" not in rec
        assert "ref" not in rec
        assert "task_type" not in rec

    def test_invalid_bubbles_up(self) -> None:
        with pytest.raises(EventLogError):
            build_record(event="bogus_event", phase="x", detail="y")


class TestAppendEvent:
    def test_creates_docs_dir(self, tmp_path: Path) -> None:
        record = build_record(
            event="phase_start", phase="architecture", detail="hi"
        )
        log = append_event(tmp_path, record)
        assert log == tmp_path / EVENT_LOG_REL
        assert log.is_file()
        assert (tmp_path / "docs").is_dir()

    def test_appends_not_overwrites(self, tmp_path: Path) -> None:
        for i in range(3):
            append_event(tmp_path, build_record(
                event="phase_start", phase="p", detail=f"#{i}",
            ))
        lines = (tmp_path / EVENT_LOG_REL).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        assert all(json.loads(line)["event"] == "phase_start" for line in lines)

    def test_rejects_invalid(self, tmp_path: Path) -> None:
        with pytest.raises(EventLogError):
            append_event(tmp_path, {
                "ts": "2026-04-23T12:00:00+00:00",
                "event": "phase_start",
                # missing phase + detail
            })
        assert not (tmp_path / EVENT_LOG_REL).exists()


class TestAppendBatch:
    def test_all_or_nothing(self, tmp_path: Path) -> None:
        good = build_record(event="phase_start", phase="x", detail="a")
        bad = {
            "ts": good["ts"],
            "event": "NOT_A_VALID_EVENT",
            "phase": "x",
            "detail": "b",
        }
        with pytest.raises(EventLogError):
            append_batch(tmp_path, [good, bad])
        # Nothing should have been written — neither record lands.
        assert not (tmp_path / EVENT_LOG_REL).exists()

    def test_preserves_existing(self, tmp_path: Path) -> None:
        append_event(tmp_path, build_record(
            event="phase_start", phase="x", detail="first",
        ))
        append_batch(tmp_path, [
            build_record(event="phase_end", phase="x", detail="2nd"),
            build_record(event="phase_start", phase="y", detail="3rd"),
        ])
        lines = (tmp_path / EVENT_LOG_REL).read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["detail"] for line in lines] == [
            "first", "2nd", "3rd"
        ]

    def test_heals_truncated_previous_line(self, tmp_path: Path) -> None:
        # Simulate a prior crash that wrote a line without trailing newline.
        log = tmp_path / EVENT_LOG_REL
        log.parent.mkdir(parents=True)
        log.write_text('{"ts":"2026-01-01T00:00:00+00:00","event":"phase_start",'
                       '"phase":"x","detail":"partial"}', encoding="utf-8")
        append_batch(tmp_path, [
            build_record(event="phase_end", phase="x", detail="after"),
        ])
        lines = log.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["detail"] == "partial"
        assert json.loads(lines[1])["detail"] == "after"

    def test_empty_batch_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(EventLogError, match="empty"):
            append_batch(tmp_path, [])


class TestParseBatchStream:
    def test_skips_blank_lines(self) -> None:
        text = (
            '\n'
            '{"event":"phase_start","phase":"x","detail":"a"}\n'
            '\n'
            '{"event":"phase_end","phase":"x","detail":"b"}\n'
        )
        recs = parse_batch_stream(text)
        assert len(recs) == 2
        # ts was auto-filled.
        assert all("ts" in r for r in recs)

    def test_invalid_json_rejected(self) -> None:
        with pytest.raises(EventLogError, match="line 1: invalid JSON"):
            parse_batch_stream('not json\n')

    def test_non_object_rejected(self) -> None:
        with pytest.raises(EventLogError, match="expected JSON object"):
            parse_batch_stream('["array", "instead"]\n')
