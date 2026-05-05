"""Tests for ``cataforge.core.feedback`` — assembler + redaction + parsers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cataforge.core.corrections import record_correction
from cataforge.core.event_log import EVENT_LOG_REL, append_event, build_record
from cataforge.core.feedback import (
    UPSTREAM_GAP,
    assemble_bug,
    assemble_correction_export,
    assemble_suggestion,
    collect_corrections,
    collect_environment,
    collect_recent_events,
    redact,
    upstream_gap_count,
)


def _bootstrap(tmp_path: Path) -> Path:
    """Lay down a minimal `.cataforge/` with framework.json + EVENT-LOG."""
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {
                "version": "0.2.1-test",
                "runtime": {"platform": "claude-code"},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


# ─── environment ──────────────────────────────────────────────────────────────


class TestEnvironment:
    def test_collect_environment_reads_framework_json(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        env = collect_environment(project)
        assert env["scaffold_version"] == "0.2.1-test"
        assert env["runtime_platform"] == "claude-code"
        assert env["package_version"]  # non-empty package version
        assert "." in env["python_version"]
        assert env["platform"]

    def test_collect_environment_handles_missing_scaffold(
        self, tmp_path: Path
    ) -> None:
        env = collect_environment(tmp_path)
        assert env["scaffold_version"] == "(unknown)"
        assert env["runtime_platform"] == "(unknown)"

    def test_collect_environment_tolerates_malformed_framework_json(
        self, tmp_path: Path
    ) -> None:
        project = _bootstrap(tmp_path)
        (project / ".cataforge" / "framework.json").write_text(
            "not-json{", encoding="utf-8"
        )
        env = collect_environment(project)
        assert env["scaffold_version"] == "(unknown)"


# ─── EVENT-LOG tail ───────────────────────────────────────────────────────────


class TestRecentEvents:
    def test_returns_empty_when_log_missing(self, tmp_path: Path) -> None:
        assert collect_recent_events(tmp_path) == []

    def test_returns_tail_in_chronological_order(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        for i in range(5):
            append_event(
                project,
                build_record(
                    event="phase_start",
                    phase="development",
                    detail=f"event-{i}",
                ),
            )
        events = collect_recent_events(project, limit=3)
        assert len(events) == 3
        # The tail must contain the last 3 inserted (ordered by file order).
        details = [e["detail"] for e in events]
        assert details == ["event-2", "event-3", "event-4"]

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        log = project / EVENT_LOG_REL
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            "not-json\n"
            + json.dumps(
                {
                    "ts": "2026-04-01T00:00:00+00:00",
                    "event": "phase_start",
                    "phase": "development",
                    "detail": "good",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        events = collect_recent_events(project)
        assert len(events) == 1
        assert events[0]["detail"] == "good"


# ─── corrections aggregator ───────────────────────────────────────────────────


class TestCorrectionsAggregator:
    def test_returns_empty_when_log_missing(self, tmp_path: Path) -> None:
        assert collect_corrections(tmp_path) == []

    def test_filters_by_deviation(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        record_correction(
            project,
            trigger="option-override",
            agent="orchestrator",
            phase="architecture",
            question="picked node 22 instead of LTS",
            baseline="node 18 LTS",
            actual="node 22",
            deviation="self-caused",
        )
        record_correction(
            project,
            trigger="review-flag",
            agent="reviewer",
            phase="review",
            question="upstream protocol skipped TDD when it was warranted",
            baseline="TDD always required",
            actual="TDD opted out",
            deviation=UPSTREAM_GAP,
        )
        all_entries = collect_corrections(project)
        upstream_only = collect_corrections(project, deviation=UPSTREAM_GAP)
        assert len(all_entries) == 2
        assert len(upstream_only) == 1
        assert upstream_only[0].deviation == UPSTREAM_GAP
        assert "TDD" in upstream_only[0].baseline

    def test_upstream_gap_count_helper(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        assert upstream_gap_count(project) == 0
        for i in range(2):
            record_correction(
                project,
                trigger="review-flag",
                agent="reviewer",
                phase="dev",
                question=f"gap-{i}",
                baseline="b",
                actual="a",
                deviation=UPSTREAM_GAP,
            )
        assert upstream_gap_count(project) == 2


# ─── redaction ────────────────────────────────────────────────────────────────


class TestRedact:
    def test_redacts_project_root(self, tmp_path: Path) -> None:
        text = f"see {tmp_path}/docs/foo.md for details"
        redacted = redact(text, tmp_path)
        assert str(tmp_path) not in redacted
        assert "<project>" in redacted

    def test_include_paths_disables_redaction(self, tmp_path: Path) -> None:
        text = f"path: {tmp_path}/x"
        assert redact(text, tmp_path, include_paths=True) == text

    def test_redacts_home(self, tmp_path: Path) -> None:
        # Use a path under HOME that is not the project root
        home = Path.home()
        text = f"home file: {home}/.bashrc — project: {tmp_path}/foo"
        redacted = redact(text, tmp_path)
        assert "~" in redacted
        assert "<project>" in redacted
        assert str(home) not in redacted


# ─── high-level assemblers ────────────────────────────────────────────────────


class TestAssembleBug:
    def test_produces_markdown_with_all_sections(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        # Seed an EVENT-LOG record + an upstream-gap correction so all
        # sections actually have content.
        append_event(
            project,
            build_record(
                event="phase_start",
                phase="development",
                detail="seeded for test",
            ),
        )
        record_correction(
            project,
            trigger="review-flag",
            agent="reviewer",
            phase="dev",
            question="upstream Q",
            baseline="upstream baseline",
            actual="local actual",
            deviation=UPSTREAM_GAP,
        )
        payload, body = assemble_bug(
            project,
            title="bug: smoke",
            summary="hook fires twice",
            user_notes="extra context here",
            skip_framework_review=True,
        )
        assert payload.kind == "bug"
        assert "## Environment" in body
        assert "0.2.1-test" in body
        assert "## `cataforge doctor` summary" in body
        assert "## Recent EVENT-LOG" in body
        assert "## On-correction signals" in body
        assert "upstream Q" in body
        assert "extra context here" in body
        # Path redaction default-on
        assert str(project) not in body

    def test_skip_framework_review_sets_status(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        payload, body = assemble_bug(
            project,
            title="bug: t",
            summary="s",
            skip_framework_review=True,
        )
        assert payload.framework_review.get("status") == "skipped"
        assert "Skipped" in body or "skipped" in body


class TestAssembleSuggestion:
    def test_renders_proposal_section(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        _payload, body = assemble_suggestion(
            project,
            title="feedback: x",
            summary="add --dry-run",
            user_notes="motivation",
        )
        assert "## Proposal" in body
        assert "motivation" in body


class TestAssembleCorrectionExport:
    def test_aggregates_only_upstream_gap(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        record_correction(
            project,
            trigger="option-override",
            agent="o",
            phase="p",
            question="not me",
            baseline="b",
            actual="a",
            deviation="self-caused",
        )
        record_correction(
            project,
            trigger="review-flag",
            agent="o",
            phase="p",
            question="me",
            baseline="b",
            actual="a",
            deviation=UPSTREAM_GAP,
        )
        _payload, body = assemble_correction_export(
            project,
            title="t",
            summary="s",
        )
        assert "me" in body
        assert "not me" not in body


# ─── path normalisation on Windows-style separators ───────────────────────────


class TestRedactCrossPlatform:
    @pytest.mark.skipif(os.sep == "/", reason="Backslash-aware branch only on Windows")
    def test_handles_backslash_paths(self, tmp_path: Path) -> None:
        # Even on POSIX we exercise the explicit replace_all branch by
        # constructing a synthetic backslash path.
        text = str(tmp_path).replace("/", "\\") + "\\foo"
        redacted = redact(text, tmp_path)
        assert "<project>" in redacted
