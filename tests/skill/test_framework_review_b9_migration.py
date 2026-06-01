"""B9 — migration_checks structural audit (path validity / deprecate order / dead entry)."""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.runtime.skill.builtins.framework_review.checks.b9 import (
    check_b9_migration_checks,
)
from cataforge.runtime.skill.builtins.framework_review.framework_check import Report


def _project(tmp_path: Path, checks: list[dict], *, editable: bool) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir(parents=True)
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "migration_checks": checks}),
        encoding="utf-8",
    )
    if editable:
        (tmp_path / "src" / "cataforge").mkdir(parents=True)
    return tmp_path


def _of(report: Report, check_id: str) -> list:
    return [f for f in report.findings if f.check_id == check_id]


def test_editable_src_path_missing_warns(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        [{"id": "mc-x", "release_version": "0.1.0", "type": "file_must_exist",
          "path": "src/cataforge/gone.py"}],
        editable=True,
    )
    report = Report()
    check_b9_migration_checks(root, report)
    hits = _of(report, "B9_migration_path_validity")
    assert len(hits) == 1
    assert hits[0].severity == "WARN"
    assert "src/" in hits[0].message


def test_downstream_src_path_missing_does_not_warn(tmp_path: Path) -> None:
    """A site-packages install has no src/ tree — the check is downstream-mute."""
    root = _project(
        tmp_path,
        [{"id": "mc-x", "release_version": "0.1.0", "type": "file_must_exist",
          "path": "src/cataforge/gone.py"}],
        editable=False,
    )
    report = Report()
    check_b9_migration_checks(root, report)
    assert _of(report, "B9_migration_path_validity") == []


def test_allow_missing_on_wrong_type_warns(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        [{"id": "mc-am", "release_version": "0.1.0", "type": "file_must_contain",
          "path": ".cataforge/x.md", "allow_missing": True, "patterns": ["x"]}],
        editable=False,
    )
    report = Report()
    check_b9_migration_checks(root, report)
    hits = _of(report, "B9_migration_path_validity")
    assert len(hits) == 1
    assert hits[0].severity == "WARN"
    assert "allow_missing" in hits[0].message


def test_allow_missing_on_correct_type_is_clean(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        [{"id": "mc-ok", "release_version": "0.1.0", "type": "file_must_not_contain",
          "path": ".cataforge/x.md", "allow_missing": True, "patterns": ["x"]}],
        editable=False,
    )
    report = Report()
    check_b9_migration_checks(root, report)
    assert _of(report, "B9_migration_path_validity") == []


def test_deprecate_at_or_before_release_warns(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        [{"id": "mc-dep", "release_version": "0.2.0", "deprecate_after": "0.2.0",
          "type": "file_must_exist", "path": ".cataforge/framework.json"}],
        editable=False,
    )
    report = Report()
    check_b9_migration_checks(root, report)
    hits = _of(report, "B9_migration_deprecate_order")
    assert len(hits) == 1
    assert hits[0].severity == "WARN"


def test_deprecated_missing_path_is_dead_entry_info(tmp_path: Path) -> None:
    """pkg version (0.6.0) > deprecate_after → the check is deprecated; absent path → INFO."""
    root = _project(
        tmp_path,
        [{"id": "mc-dead", "release_version": "0.1.0", "deprecate_after": "0.2.0",
          "type": "file_must_exist", "path": ".cataforge/gone.md"}],
        editable=False,
    )
    report = Report()
    check_b9_migration_checks(root, report)
    hits = _of(report, "B9_migration_dead_entry")
    assert len(hits) == 1
    assert hits[0].severity == "INFO"
    # A deprecated entry skips the live-path checks.
    assert _of(report, "B9_migration_path_validity") == []


def test_live_editable_check_with_present_src_path_is_clean(tmp_path: Path) -> None:
    root = _project(
        tmp_path,
        [{"id": "mc-clean", "release_version": "99.0.0", "type": "dir_must_contain_files",
          "path": "src/cataforge"}],
        editable=True,
    )
    report = Report()
    check_b9_migration_checks(root, report)
    assert report.findings == []


def test_no_migration_checks_section_is_noop(tmp_path: Path) -> None:
    cf = tmp_path / ".cataforge"
    cf.mkdir(parents=True)
    (cf / "framework.json").write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
    report = Report()
    check_b9_migration_checks(tmp_path, report)
    assert report.findings == []
