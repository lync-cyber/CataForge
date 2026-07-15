"""Tests for ``cataforge.application.feedback`` — assembler + redaction + parsers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cataforge.application.feedback import (
    UPSTREAM_GAP,
    assemble_bug,
    assemble_correction_export,
    assemble_suggestion,
    collect_corrections,
    collect_environment,
    collect_recent_events,
    derive_doc_id,
    redact,
    upstream_gap_count,
)
from cataforge.core.corrections import CORRECTIONS_LOG_REL, record_correction
from cataforge.core.event_log import (
    EVENT_LOG_REL,
    MAX_EVENTLOG_BYTES,
    append_event,
    build_record,
)


class TestLayering:
    """``application/feedback`` must not statically import from ``cataforge.interface.cli``.

    ``interface`` sits above ``application`` in the layered graph, so a
    module-level import would invert the dependency direction.
    """

    def test_no_static_cli_import(self) -> None:
        from cataforge.application import feedback

        pkg_dir = Path(feedback.__file__).parent
        for src_file in sorted(pkg_dir.glob("*.py")):
            source = src_file.read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.lstrip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                # Lazy imports inside function bodies are indented — skip them.
                if line.startswith((" ", "\t")):
                    continue
                assert "cataforge.interface.cli" not in line, (
                    f"{src_file.name} must not statically import from "
                    f"cataforge.interface.cli; offending line: {line!r}"
                )

    def test_doctor_summary_lives_in_services(self) -> None:
        from cataforge.application.services import doctor_summary

        assert hasattr(doctor_summary, "collect_doctor_summary")


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

    def test_collect_environment_handles_missing_scaffold(self, tmp_path: Path) -> None:
        env = collect_environment(tmp_path)
        assert env["scaffold_version"] == "(unknown)"
        assert env["runtime_platform"] == "(unknown)"

    def test_collect_environment_tolerates_malformed_framework_json(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        (project / ".cataforge" / "framework.json").write_text("not-json{", encoding="utf-8")
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

    def test_oversized_log_returns_empty_and_warns(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        log = project / EVENT_LOG_REL
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(b"x" * (MAX_EVENTLOG_BYTES + 1))
        with patch("cataforge.application.feedback.collectors.logger") as mock_log:
            events = collect_recent_events(project)
            assert mock_log.warning.called
        assert events == []


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

    def test_annotated_deviation_still_classifies(self, tmp_path: Path) -> None:
        """A 偏差类型 value with an inline parenthetical annotation must still
        classify by its leading token. ``record_correction`` rejects such
        values, so the historical / hand-written form is written raw here."""
        project = _bootstrap(tmp_path)
        log = project / CORRECTIONS_LOG_REL
        log.parent.mkdir(parents=True, exist_ok=True)

        def _entry(d: str, deviation: str) -> str:
            return (
                f"### {d} | tech-lead | development\n"
                "- 触发信号: review-flag\n"
                "- 问题/假设: q\n"
                "- 基线/推荐: b\n"
                "- 实际/选择: a\n"
                f"- 偏差类型: {deviation}\n"
            )

        log.write_text(
            "---\nid: corrections-log\n---\n# Corrections Log\n"
            + _entry("2026-06-10", "upstream-gap")
            + _entry("2026-06-11", "upstream-gap (dev-plan 漏 M-002↔M-003 集成点)")
            + _entry("2026-06-12", "upstream-gap（全角注释）"),
            encoding="utf-8",
        )

        entries = collect_corrections(project, deviation=UPSTREAM_GAP)
        assert len(entries) == 3
        assert all(e.deviation == UPSTREAM_GAP for e in entries)
        assert upstream_gap_count(project) == 3

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


class TestCollectFrameworkReviewExceptionHandling:
    """C5: import failure vs runner runtime failure must surface as
    *distinct* status / reason / payload shapes so the upstream bug
    report can tell whether the skill subsystem is missing entirely
    or simply crashed on this run."""

    def test_import_failure_returns_runner_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Force the ``from cataforge.runtime.skill.runner import SkillRunner``
        line to raise ImportError. Result must carry ``status=skipped``
        and a reason starting with ``runner-unavailable:`` — *not* the
        runtime-error branch's ``runner-failed:``."""
        import sys

        from cataforge.application import feedback as feedback_mod

        # Wipe any cached import so the first attempt actually re-runs.
        monkeypatch.delitem(sys.modules, "cataforge.runtime.skill.runner", raising=False)

        class _Blocker:
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "cataforge.runtime.skill.runner":
                    raise ImportError("simulated missing dep")
                return None

        blocker = _Blocker()
        monkeypatch.setattr(sys, "meta_path", [blocker, *sys.meta_path])

        # Project must exist (later check is `.cataforge.is_dir()`).
        (tmp_path / ".cataforge").mkdir()

        result = feedback_mod.collect_framework_review(tmp_path)
        assert result["status"] == "skipped"
        assert result["reason"].startswith("runner-unavailable:"), result
        # The traceback key only exists on the runtime-error branch.
        assert "traceback" not in result

    def test_runtime_failure_returns_error_with_traceback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real SkillRunner that raises at .run() time must surface
        as ``status=error`` with both a reason and a traceback the bug
        report can paste straight through."""
        from cataforge.application import feedback as feedback_mod

        (tmp_path / ".cataforge").mkdir()

        class _BrokenRunner:
            def __init__(self, *, project_root):
                self._root = project_root

            def run(self, *_a, **_kw):
                raise RuntimeError("simulated runner crash")

        # Patch the symbol on the actual runner module so the
        # in-function import inside collect_framework_review picks it up.
        from cataforge.runtime.skill import runner as runner_mod

        monkeypatch.setattr(runner_mod, "SkillRunner", _BrokenRunner)

        result = feedback_mod.collect_framework_review(tmp_path)
        assert result["status"] == "error"
        assert result["reason"].startswith("runner-failed:")
        assert "RuntimeError" in result["reason"]
        assert "simulated runner crash" in result["reason"]
        assert "traceback" in result
        assert "simulated runner crash" in result["traceback"]


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


# ─── YAML front matter (issue #115 P5) ────────────────────────────────────────


class TestRenderFrontMatter:
    """All three assemblers must prepend a doc-indexer-compatible YAML block.

    The --out flag must write a body whose first non-blank line is valid YAML
    front matter containing ``doc_type`` / ``status`` / ``id``; otherwise
    ``docs validate`` flags the output as an orphan.
    """

    @staticmethod
    def _assert_valid_frontmatter(body: str, *, expected_id_contains: str) -> None:
        lines = body.splitlines()
        assert lines[0] == "---", f"first line was {lines[0]!r}, expected '---'"
        # Front matter must close with a `---` line before any markdown.
        try:
            end = lines.index("---", 1)
        except ValueError:
            raise AssertionError("front matter has no closing '---'") from None
        block = "\n".join(lines[1:end])
        assert "doc_type: framework-feedback" in block
        assert "status: approved" in block
        assert "deps: []" in block
        assert "id: " in block
        assert expected_id_contains in block

    def test_bug_bundle_has_frontmatter(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        _payload, body = assemble_bug(
            project,
            title="bug: hook fires twice on resume",
            summary="seen on 0.4.0",
            skip_framework_review=True,
        )
        self._assert_valid_frontmatter(body, expected_id_contains="hook-fires-twice")

    def test_suggest_bundle_has_frontmatter(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        _payload, body = assemble_suggestion(
            project,
            title="feedback: add --dry-run to triage",
            summary="self-explanatory",
        )
        self._assert_valid_frontmatter(body, expected_id_contains="add-dry-run")

    def test_correction_export_bundle_has_frontmatter(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        record_correction(
            project,
            trigger="review-flag",
            agent="reviewer",
            phase="dev",
            question="q",
            baseline="b",
            actual="a",
            deviation=UPSTREAM_GAP,
        )
        _payload, body = assemble_correction_export(
            project,
            title="feedback: 3 upstream-gap signals",
            summary="aggregated",
        )
        self._assert_valid_frontmatter(body, expected_id_contains="upstream-gap-signals")


class TestDeriveDocId:
    """``derive_doc_id`` slug rules (must satisfy ``DOC_ID_RE`` ^[\\w-]+$)."""

    def test_lowercases_and_replaces_punct(self) -> None:
        slug = derive_doc_id("feedback: TDD light-mode threshold off!", kind="suggest")
        # Should be lowercase, no `:`, no `!`, hyphens collapsed.
        assert slug == "feedback-suggest-tdd-light-mode-threshold-off"

    def test_strips_leading_trailing_hyphens(self) -> None:
        slug = derive_doc_id("!!!hello world!!!", kind="bug")
        assert slug == "feedback-bug-hello-world"
        assert not slug.endswith("-")
        assert not slug.startswith("-")

    def test_falls_back_to_date_when_title_empty(self) -> None:
        slug = derive_doc_id("###", kind="bug")
        # 8-digit YYYYMMDD stamp suffix
        assert slug.startswith("feedback-bug-")
        assert len(slug.split("-")[-1]) == 8

    def test_does_not_double_prefix(self) -> None:
        slug = derive_doc_id("feedback-bug-already-prefixed", kind="bug")
        assert slug == "feedback-bug-already-prefixed"

    def test_id_matches_doc_id_re(self) -> None:
        from cataforge.domain.docs.patterns import DOC_ID_RE

        for title in [
            "feedback: TDD light-mode threshold off",
            "Bug — hook fires twice (0.4.0)",
            "建议：加 dry-run 模式",
        ]:
            slug = derive_doc_id(title, kind="suggest")
            assert DOC_ID_RE.match(slug), f"{slug!r} from {title!r} fails DOC_ID_RE"

    def test_folds_non_ascii_to_ascii(self) -> None:
        slug = derive_doc_id(
            "bug: sprint-review Layer 1 builtins 与 dev-plan 模板格式失配", kind="bug"
        )
        assert slug.isascii(), slug
        assert "sprint-review" in slug
        assert "dev-plan" in slug

    def test_all_non_ascii_title_falls_back_to_date(self) -> None:
        slug = derive_doc_id("全中文标题没有任何拉丁字符", kind="bug")
        assert slug.startswith("feedback-bug-")
        assert len(slug.split("-")[-1]) == 8

    def test_caps_length_at_hyphen_boundary(self) -> None:
        slug = derive_doc_id("word " * 40, kind="bug")
        assert len(slug) <= 100, f"slug too long ({len(slug)}): {slug!r}"
        assert not slug.endswith("-")
