"""Tests for the shared CORRECTIONS-LOG / EVENT-LOG writer."""

from __future__ import annotations

import json
from datetime import UTC
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

    # Front matter present so `cataforge docs index` ingests this file
    # instead of treating it as an orphan (would fail `cataforge doctor`).
    assert text.startswith("---\n"), "log must lead with YAML front matter"
    assert 'id: "corrections-log"' in text
    assert "doc_type: correction-log" in text
    assert "status: approved" in text

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


def test_record_correction_date_uses_utc(tmp_path: Path) -> None:
    """Markdown date must match EVENT-LOG (which writes UTC). Naive
    local-time was producing a one-day skew for evening corrections in
    CST etc — the markdown row and the paired EVENT-LOG entry then
    grep-by-date to different files."""
    from datetime import datetime

    expected = datetime.now(UTC).strftime("%Y-%m-%d")
    record_correction(
        tmp_path,
        trigger="option-override",
        agent="orchestrator",
        phase="x",
        question="q",
        baseline="b",
        actual="a",
    )
    text = (tmp_path / CORRECTIONS_LOG_REL).read_text(encoding="utf-8")
    assert f"### {expected} " in text, (
        f"correction header must start with the UTC date {expected!r}; found {text!r}"
    )


def test_first_call_atomic_failure_leaves_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-fix shape: the first call wrote ``_HEADER`` then ``entry`` in
    two consecutive ``f.write`` calls inside a ``"w"`` open(). A crash
    after the header (FS full / OS kill / power) left a header-only
    file with no entry — and the next call's ``is_file()`` check
    skipped the header branch, so a CORRECTIONS-LOG could end up in
    production with no Header / 不齐全 entries forever.

    Post-fix: ``atomic_write_text`` either writes the complete header
    + entry or leaves the file absent entirely.
    """
    import os

    log_path = tmp_path / "docs" / "reviews" / "CORRECTIONS-LOG.md"
    assert not log_path.exists()

    def _boom(*_a, **_kw):
        raise OSError("simulated mid-write failure")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError, match="simulated"):
        record_correction(
            tmp_path,
            trigger="option-override",
            agent="orchestrator",
            phase="x",
            question="q",
            baseline="b",
            actual="a",
            write_event_log=False,
        )

    assert not log_path.exists(), (
        "atomic write must leave no file when the rename failed; pre-fix "
        "this could exit with a header-only file in production."
    )
    # No temp residue either.
    parent = log_path.parent
    if parent.exists():
        residue = [p for p in parent.iterdir() if p.name.startswith(".CORRECTIONS-LOG.md.")]
        assert residue == [], f"atomic temp file leaked: {residue!r}"


def test_second_call_atomic_failure_preserves_existing_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First entry lands cleanly; a crash during the SECOND entry's
    rename must leave the prior log intact (header + first entry),
    never a truncated / appended-half state. With the new
    read-modify-write through ``atomic_write_text`` this is the
    natural behaviour."""
    import os

    record_correction(
        tmp_path,
        trigger="option-override",
        agent="orchestrator",
        phase="x",
        question="first",
        baseline="b1",
        actual="a1",
        write_event_log=False,
    )
    log_path = tmp_path / "docs" / "reviews" / "CORRECTIONS-LOG.md"
    first_state = log_path.read_text(encoding="utf-8")
    assert "first" in first_state
    assert "# Corrections Log" in first_state

    def _boom(*_a, **_kw):
        raise OSError("simulated mid-write failure")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError, match="simulated"):
        record_correction(
            tmp_path,
            trigger="review-flag",
            agent="reviewer",
            phase="review",
            question="second",
            baseline="b2",
            actual="a2",
            write_event_log=False,
        )

    after = log_path.read_text(encoding="utf-8")
    assert after == first_state, (
        "second-write failure must leave the prior log byte-for-byte intact"
    )
    assert "second" not in after


def test_record_correction_accepts_upstream_gap_deviation(tmp_path: Path) -> None:
    """``upstream-gap`` is the deviation type that powers the framework-feedback
    aggregator. Round-trip it through the writer + markdown re-read to make
    sure the new enum value flows end-to-end."""
    result = record_correction(
        tmp_path,
        trigger="review-flag",
        agent="reviewer",
        phase="review",
        question="upstream baseline missed the GitOps case",
        baseline="A: monorepo",
        actual="B: gitops",
        deviation="upstream-gap",
    )
    text = (tmp_path / result["corrections_log"].relative_to(tmp_path)).read_text(encoding="utf-8")
    assert "偏差类型: upstream-gap" in text
    # And it should be visible to the downstream aggregator.
    from cataforge.application.feedback import collect_corrections

    entries = collect_corrections(tmp_path, deviation="upstream-gap")
    assert len(entries) == 1
    assert entries[0].deviation == "upstream-gap"
    assert entries[0].baseline == "A: monorepo"
    assert entries[0].actual == "B: gitops"
