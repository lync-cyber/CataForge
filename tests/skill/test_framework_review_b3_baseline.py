"""B3-γ baseline provenance + B3-β placeholder-template skip."""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.runtime.skill.builtins.framework_review.framework_check import (
    Report,
    check_b3_baseline_provenance,
    check_b3_rules_schema,
)
from cataforge.utils.run_subprocess import run as run_proc


def _git(root: Path, *args: str) -> None:
    result = run_proc(["git", *args], cwd=root)
    assert result.returncode == 0, result.stderr


def _git_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")


def _write_baseline(root: Path) -> Path:
    path = root / ".cataforge" / "baselines" / "complexity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "metrics": {}}) + "\n", encoding="utf-8")
    return path


def _write_scan_report(root: Path) -> Path:
    path = root / "docs" / "reviews" / "code" / "CODE-SCAN-20260701-r1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nid: code-scan\n---\nreport\n", encoding="utf-8")
    return path


def _fails(report: Report) -> list[str]:
    return [f.location for f in report.findings if f.check_id == "B3_baseline_provenance"]


def test_no_baselines_dir_is_silent(tmp_path: Path) -> None:
    report = Report()
    check_b3_baseline_provenance(tmp_path, report)
    assert report.findings == []


def test_dirty_baseline_without_report_fails(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "seed.txt").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    _write_baseline(tmp_path)  # uncommitted, no report change
    report = Report()
    check_b3_baseline_provenance(tmp_path, report)
    assert _fails(report) == [".cataforge/baselines/complexity.json"]


def test_dirty_baseline_with_dirty_report_passes(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "seed.txt").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    _write_baseline(tmp_path)
    _write_scan_report(tmp_path)  # both uncommitted together
    report = Report()
    check_b3_baseline_provenance(tmp_path, report)
    assert _fails(report) == []


def test_committed_baseline_without_report_fails(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    _write_baseline(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "baseline only")
    report = Report()
    check_b3_baseline_provenance(tmp_path, report)
    fails = _fails(report)
    assert fails == [".cataforge/baselines/complexity.json"]


def test_committed_baseline_with_report_passes(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    _write_baseline(tmp_path)
    _write_scan_report(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "scan refresh + report")
    report = Report()
    check_b3_baseline_provenance(tmp_path, report)
    assert _fails(report) == []


def test_non_git_root_is_skipped(tmp_path: Path, monkeypatch: object) -> None:
    _write_baseline(tmp_path)
    # No git repo at tmp_path; _git_lines returns None via non-zero exit
    # (git walks up — guard by GIT_CEILING so a host repo above /tmp can't leak in).
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    report = Report()
    check_b3_baseline_provenance(tmp_path, report)
    assert report.findings == []


def test_b3_rules_schema_skips_placeholder_template(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".cataforge" / "skills" / "code-review" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "arch.yaml").write_text(
        "# schema_version: 2\n# scope: project\n# rule_type: arch\n", encoding="utf-8"
    )
    report = Report()
    check_b3_rules_schema(tmp_path, report)
    assert report.findings == []
