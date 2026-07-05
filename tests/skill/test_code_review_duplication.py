"""Duplication dimension: built-in floor + jscpd augmentation (Track A).

The dimension is owned by one check symmetric with complexity_gate — a
zero-dependency built-in floor guarantees it is never dark, and jscpd
augments with a richer signal when it produces a report. jscpd that can't
run (absent, or a Windows .cmd shim that no-ops under subprocess) falls
through to the floor rather than vanishing or emitting a misleading WARN.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.runtime.skill.builtins.code_review.checks import duplication
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding

_BLOCK = "\n".join(
    [
        "def compute_totals(rows):",
        "    total = 0",
        "    for row in rows:",
        "        total += row.value",
        "        total += row.tax",
        "    return total",
    ]
)


def _ctx(root: Path, mode: str = "scan") -> CheckContext:
    return CheckContext(target=root, project_root=root, mode=mode)


def _write_report(workdir: Path, clones: int, percentage: float) -> Path:
    dups = [
        {
            "lines": 12 + i,
            "firstFile": {"name": f"a/mod{i}.py", "start": 10},
            "secondFile": {"name": f"b/mod{i}.py", "start": 20},
        }
        for i in range(clones)
    ]
    report = workdir / "jscpd-report.json"
    report.write_text(
        json.dumps(
            {
                "duplicates": dups,
                "statistics": {"total": {"percentage": percentage, "clones": clones}},
            }
        ),
        encoding="utf-8",
    )
    return report


# ---- jscpd report parsing ----------------------------------------------------


def test_parse_jscpd_report_structured(tmp_path: Path) -> None:
    report = _write_report(tmp_path, clones=154, percentage=2.43)
    findings = duplication.parse_jscpd_report(report)
    assert len(findings) == 1
    assert findings[0].check_id == "code_review.duplication"
    assert findings[0].category == "duplication"
    assert "154" in findings[0].detail  # real count surfaced, not a blob
    assert "2.43" in findings[0].detail  # ratio surfaced


def test_parse_jscpd_report_clean_is_empty(tmp_path: Path) -> None:
    report = _write_report(tmp_path, clones=0, percentage=0.0)
    assert duplication.parse_jscpd_report(report) == []


@pytest.mark.parametrize(("pct", "severity"), [(0.4, "info"), (12.0, "warn")])
def test_parse_jscpd_ratio_drives_severity(tmp_path: Path, pct: float, severity: str) -> None:
    report = _write_report(tmp_path, clones=3, percentage=pct)
    assert duplication.parse_jscpd_report(report)[0].severity == severity


# ---- built-in floor ----------------------------------------------------------


def test_builtin_floor_detects_cross_file_clone(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(_BLOCK + "\n\nx = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n\n" + _BLOCK + "\n", encoding="utf-8")
    findings = duplication.builtin_floor(_ctx(tmp_path))
    assert len(findings) == 1
    assert findings[0].category == "duplication"
    assert "a.py" in findings[0].detail and "b.py" in findings[0].detail


def test_builtin_floor_silent_when_no_duplication(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def f():\n    return 42\n", encoding="utf-8")
    assert duplication.builtin_floor(_ctx(tmp_path)) == []


# ---- dimension ownership (jscpd primary → builtin floor) ----------------------


def test_run_uses_jscpd_when_it_produces_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.py").write_text(_BLOCK + "\n", encoding="utf-8")
    rich = [Finding("code_review.duplication", "info", "duplication", "jscpd: 9 clones")]
    monkeypatch.setattr(duplication, "_jscpd_findings", lambda ctx: rich)
    assert duplication.run(_ctx(tmp_path)) == rich


def test_run_falls_back_to_floor_when_jscpd_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.py").write_text(_BLOCK + "\n\nx = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n\n" + _BLOCK + "\n", encoding="utf-8")
    # jscpd unavailable / produced no report → None → floor owns the dimension
    monkeypatch.setattr(duplication, "_jscpd_findings", lambda ctx: None)
    findings = duplication.run(_ctx(tmp_path))
    assert len(findings) == 1
    assert "builtin floor" in findings[0].detail


def test_run_review_mode_noop(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(_BLOCK + "\n", encoding="utf-8")
    assert duplication.run(_ctx(tmp_path, mode="review")) == []


def test_jscpd_findings_none_when_tool_unavailable(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    ctx = CheckContext(
        target=tmp_path, project_root=tmp_path, mode="scan", tool_cache={"jscpd": False}
    )
    assert duplication._jscpd_findings(ctx) is None
