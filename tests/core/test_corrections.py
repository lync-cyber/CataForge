"""Tests for the shared CORRECTIONS-LOG / EVENT-LOG writer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.corrections import CORRECTIONS_LOG_REL, record_correction


def test_record_correction_creates_log_with_header(tmp_path: Path) -> None:
    result = record_correction(
        tmp_path,
        trigger="option-override",
        agent="orchestrator",
        phase="architecture",
        question="Q1: 选择打包策略",
        baseline="C: 单仓库",
        actual="A: 多包",
        deviation="preference",
    )

    log_path = tmp_path / CORRECTIONS_LOG_REL
    assert result["corrections_log"] == log_path
    text = log_path.read_text(encoding="utf-8")

    assert "# Corrections Log" in text
    assert "On-Correction Learning Protocol" in text
    assert "orchestrator" in text
    assert "option-override" in text
    assert "Q1: 选择打包策略" in text
    assert "C: 单仓库" in text
    assert "A: 多包" in text
    assert "偏差类型: preference" in text


def test_record_correction_appends_to_existing_log(tmp_path: Path) -> None:
    record_correction(
        tmp_path,
        trigger="option-override",
        agent="orchestrator",
        phase="architecture",
        question="first",
        baseline="X",
        actual="Y",
    )
    record_correction(
        tmp_path,
        trigger="review-flag",
        agent="reviewer",
        phase="review",
        question="second",
        baseline="A",
        actual="B",
        deviation="self-caused",
    )

    text = (tmp_path / CORRECTIONS_LOG_REL).read_text(encoding="utf-8")
    assert text.count("# Corrections Log") == 1, "header should not duplicate"
    assert "first" in text and "second" in text
    assert text.count("###") == 2


def test_record_correction_dual_writes_event_log(tmp_path: Path) -> None:
    result = record_correction(
        tmp_path,
        trigger="interrupt-override",
        agent="orchestrator",
        phase="architecture",
        question="Q3: Node 版本",
        baseline="B: 18 LTS",
        actual="C: 22 LTS",
        deviation="self-caused",
    )

    event_path = tmp_path / "docs" / "EVENT-LOG.jsonl"
    assert result["event_log"] == event_path
    assert event_path.is_file()

    record = json.loads(event_path.read_text(encoding="utf-8").strip())
    assert record["event"] == "correction"
    assert record["agent"] == "orchestrator"
    assert record["phase"] == "architecture"
    assert "interrupt-override" in record["detail"]


def test_record_correction_skips_event_log_when_disabled(tmp_path: Path) -> None:
    result = record_correction(
        tmp_path,
        trigger="option-override",
        agent="orchestrator",
        phase="architecture",
        question="x",
        baseline="y",
        actual="z",
        write_event_log=False,
    )
    assert result["event_log"] is None
    assert not (tmp_path / "docs" / "EVENT-LOG.jsonl").exists()


def test_record_correction_rejects_bad_trigger(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="trigger="):
        record_correction(
            tmp_path,
            trigger="bogus",
            agent="orchestrator",
            phase="x",
            question="q",
            baseline="b",
            actual="a",
        )


def test_record_correction_rejects_bad_deviation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="deviation="):
        record_correction(
            tmp_path,
            trigger="option-override",
            agent="orchestrator",
            phase="x",
            question="q",
            baseline="b",
            actual="a",
            deviation="bogus",
        )
