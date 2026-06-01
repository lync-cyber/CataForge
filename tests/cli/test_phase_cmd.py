"""Tests for ``cataforge phase status``."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.interface.cli.main import cli
from cataforge.interface.cli.phase_cmd import (
    evaluate_phase,
    indexed_doc_types,
    is_placeholder,
    parse_current_phase,
    parse_doc_status,
    parse_phase_starts,
)

PLACEHOLDER = (
    "{requirements|architecture|ui_design|dev_planning"
    "|development|testing|deployment|completed}"
)


def _state(phase: str, doc_status: dict[str, str] | None = None) -> str:
    lines = [
        "# Proj",
        "## 项目状态",
        f"- 当前阶段: {phase}",
        "- 文档状态:",
    ]
    for dt, st in (doc_status or {}).items():
        lines.append(f"  - {dt}: {st}")
    return "\n".join(lines) + "\n"


def _make_project(
    tmp: Path,
    phase: str,
    *,
    doc_status: dict[str, str] | None = None,
    prd_file: bool = False,
    indexed: bool = False,
    phase_start: str | None = None,
) -> Path:
    (tmp / ".cataforge").mkdir()
    (tmp / "CLAUDE.md").write_text(_state(phase, doc_status), encoding="utf-8")
    docs = tmp / "docs"
    docs.mkdir()
    if prd_file:
        (docs / "prd.md").write_text("# prd\n", encoding="utf-8")
    if indexed:
        (docs / ".doc-index.json").write_text(
            json.dumps({"documents": {"prd-x": {"file_path": "docs/prd.md", "doc_type": "prd"}}}),
            encoding="utf-8",
        )
    if phase_start:
        rec = {
            "ts": "2026-01-01T00:00:00+00:00",
            "event": "phase_start",
            "phase": phase_start,
            "detail": "x",
        }
        (docs / "EVENT-LOG.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return tmp


class TestParsers:
    def test_parse_current_phase(self) -> None:
        assert parse_current_phase("- 当前阶段: requirements\n") == "requirements"
        assert parse_current_phase("no phase line") is None

    def test_is_placeholder(self) -> None:
        assert is_placeholder(PLACEHOLDER)
        assert is_placeholder(None)
        assert not is_placeholder("requirements")

    def test_parse_doc_status(self) -> None:
        text = _state("requirements", {"prd": "draft", "arch": "未开始"})
        status = parse_doc_status(text)
        assert status["prd"] == "draft"
        assert status["arch"] == "未开始"

    def test_parse_phase_starts(self) -> None:
        log = (
            json.dumps({"event": "phase_start", "phase": "requirements", "detail": "x"})
            + "\n"
            + json.dumps({"event": "state_change", "phase": "development", "detail": "y"})
            + "\n"
        )
        assert parse_phase_starts(log) == {"requirements"}

    def test_indexed_doc_types(self) -> None:
        idx = json.dumps({"documents": {"a": {"doc_type": "arch"}, "b": {"doc_type": "prd"}}})
        assert indexed_doc_types(idx) == {"arch", "prd"}


class TestEvaluatePhase:
    def test_placeholder_fails(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, PLACEHOLDER)
        _current, checks = evaluate_phase(root)
        assert any(label == "workflow driven" and not ok for label, ok, _ in checks)

    def test_driven_requirements_with_prd_passes(self, tmp_path: Path) -> None:
        root = _make_project(
            tmp_path,
            "requirements",
            doc_status={"prd": "draft"},
            prd_file=True,
            indexed=True,
            phase_start="requirements",
        )
        _current, checks = evaluate_phase(root)
        assert all(ok for _label, ok, _ in checks), checks

    def test_driven_but_doc_missing_fails(self, tmp_path: Path) -> None:
        root = _make_project(
            tmp_path, "requirements", doc_status={"prd": "未开始"}, phase_start="requirements"
        )
        _current, checks = evaluate_phase(root)
        assert any("doc present" in label and not ok for label, ok, _ in checks)
        assert any("doc status" in label and not ok for label, ok, _ in checks)


class TestPhaseStatusCli:
    def test_placeholder_exit_1(self, tmp_path: Path) -> None:
        _make_project(tmp_path, PLACEHOLDER)
        result = CliRunner().invoke(cli, ["--project-dir", str(tmp_path), "phase", "status"])
        assert result.exit_code == 1

    def test_driven_exit_0(self, tmp_path: Path) -> None:
        _make_project(
            tmp_path,
            "requirements",
            doc_status={"prd": "draft"},
            prd_file=True,
            indexed=True,
            phase_start="requirements",
        )
        result = CliRunner().invoke(cli, ["--project-dir", str(tmp_path), "phase", "status"])
        assert result.exit_code == 0, result.output

    def test_no_state_exit_2(self, tmp_path: Path) -> None:
        (tmp_path / ".cataforge").mkdir()
        result = CliRunner().invoke(cli, ["--project-dir", str(tmp_path), "phase", "status"])
        assert result.exit_code == 2
