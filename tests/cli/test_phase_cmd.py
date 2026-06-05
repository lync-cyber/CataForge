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
    "{requirements|architecture|ui_design|dev_planning|development|testing|deployment|completed}"
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


def _make_subdir_project(
    tmp: Path,
    phase: str,
    doc_type: str,
    *,
    filename: str,
    doc_status: dict[str, str] | None = None,
) -> Path:
    """Project whose primary doc lives under ``docs/{doc_type}/`` (the layout
    ``context generate`` actually writes), fully driven for ``phase``."""
    (tmp / ".cataforge").mkdir()
    (tmp / "CLAUDE.md").write_text(_state(phase, doc_status), encoding="utf-8")
    docs = tmp / "docs"
    subdir = docs / doc_type
    subdir.mkdir(parents=True)
    (subdir / filename).write_text(f"# {doc_type}\n", encoding="utf-8")
    (docs / ".doc-index.json").write_text(
        json.dumps(
            {
                "documents": {
                    filename.removesuffix(".md"): {
                        "file_path": f"docs/{doc_type}/{filename}",
                        "doc_type": doc_type,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    rec = {
        "ts": "2026-01-01T00:00:00+00:00",
        "event": "phase_start",
        "phase": phase,
        "detail": "x",
    }
    (docs / "EVENT-LOG.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return tmp


def _make_multi_doc_project(
    tmp: Path,
    phase: str,
    docs: dict[str, str],  # doc_type -> filename
    *,
    doc_status: dict[str, str],
) -> Path:
    """Project with one authored doc per ``doc_type`` under ``docs/{doc_type}/``,
    each carrying a matching frontmatter ``doc_type``; fully driven for ``phase``."""
    (tmp / ".cataforge").mkdir()
    (tmp / "CLAUDE.md").write_text(_state(phase, doc_status), encoding="utf-8")
    docs_dir = tmp / "docs"
    docs_dir.mkdir()
    documents: dict[str, dict[str, str]] = {}
    for doc_type, filename in docs.items():
        subdir = docs_dir / doc_type
        subdir.mkdir(parents=True)
        (subdir / filename).write_text(
            f"---\ndoc_type: {doc_type}\nmode: agile-lite\n---\n# {doc_type}\n", encoding="utf-8"
        )
        documents[filename.removesuffix(".md")] = {
            "file_path": f"docs/{doc_type}/{filename}",
            "doc_type": doc_type,
        }
    (docs_dir / ".doc-index.json").write_text(
        json.dumps({"documents": documents}), encoding="utf-8"
    )
    rec = {
        "ts": "2026-01-01T00:00:00+00:00",
        "event": "phase_start",
        "phase": phase,
        "detail": "x",
    }
    (docs_dir / "EVENT-LOG.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return tmp


class TestAgileModePhases:
    def test_planning_is_recognised(self) -> None:
        from cataforge.interface.cli.phase_cmd import PHASES

        assert "planning" in PHASES
        assert "brief" in PHASES

    def test_agile_lite_planning_gates_on_prd_and_arch(self, tmp_path: Path) -> None:
        # agile-lite planning fuses requirements+architecture → both prd and arch.
        root = _make_multi_doc_project(
            tmp_path,
            "planning",
            {
                "prd": "prd-lite-temperature-converter.md",
                "arch": "arch-lite-temperature-converter.md",
            },
            doc_status={"prd": "draft", "arch": "draft"},
        )
        _current, checks = evaluate_phase(root)
        assert all(ok for _label, ok, _ in checks), checks

    def test_agile_lite_planning_missing_prd_fails(self, tmp_path: Path) -> None:
        # Only arch authored — the fused planning gate must still flag prd.
        root = _make_multi_doc_project(
            tmp_path,
            "planning",
            {"arch": "arch-lite-temperature-converter.md"},
            doc_status={"arch": "draft"},
        )
        _current, checks = evaluate_phase(root)
        assert any("prd doc present" in label and not ok for label, ok, _ in checks), checks

    def test_agile_prototype_brief_subdir_doc_passes(self, tmp_path: Path) -> None:
        root = _make_subdir_project(
            tmp_path,
            "brief",
            "brief",
            filename="brief-temperature-converter.md",
            doc_status={"brief": "draft"},
        )
        _current, checks = evaluate_phase(root)
        assert all(ok for _label, ok, _ in checks), checks

    def test_subdir_doc_satisfies_present_check(self, tmp_path: Path) -> None:
        # Regression: the present check scanned only flat docs/{type}.md, so a
        # subdir-authored doc was reported missing even while indexed OK.
        root = _make_subdir_project(
            tmp_path,
            "requirements",
            "prd",
            filename="prd-x.md",
            doc_status={"prd": "draft"},
        )
        _current, checks = evaluate_phase(root)
        present = next((c for c in checks if "doc present" in c[0]), None)
        assert present is not None and present[1], checks
        assert present[2] == "docs/prd/prd-x.md"

    def test_present_excludes_mismatched_frontmatter_doc(self, tmp_path: Path) -> None:
        # A doc explicitly declaring a different frontmatter doc_type, misplaced
        # under docs/prd/, must not satisfy the prd present gate.
        (tmp_path / ".cataforge").mkdir()
        (tmp_path / "CLAUDE.md").write_text(
            _state("requirements", {"prd": "draft"}), encoding="utf-8"
        )
        docs = tmp_path / "docs"
        (docs / "prd").mkdir(parents=True)
        (docs / "prd" / "stray.md").write_text(
            "---\ndoc_type: arch\n---\n# stray\n", encoding="utf-8"
        )
        (docs / ".doc-index.json").write_text(
            json.dumps(
                {"documents": {"prd-x": {"file_path": "docs/prd/stray.md", "doc_type": "prd"}}}
            ),
            encoding="utf-8",
        )
        rec = {
            "ts": "2026-01-01T00:00:00+00:00",
            "event": "phase_start",
            "phase": "requirements",
            "detail": "x",
        }
        (docs / "EVENT-LOG.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")

        _current, checks = evaluate_phase(tmp_path)
        present = next((c for c in checks if "prd doc present" in c[0]), None)
        assert present is not None and not present[1], checks


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
