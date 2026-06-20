"""task-dep-analysis CLI: ``--format json`` analysis kept, mermaid removed.

The mermaid visualisation surface moved to ``cataforge viz tasks`` (see
tests/cli/test_viz_cmd.py::TestVizTasks); this module pins the analysis
responsibility that stays here plus the rejection of the retired format.
"""

from __future__ import annotations

import json
import subprocess
import sys

_MODULE = "cataforge.runtime.skill.builtins.task_dep_analysis.task_dep_analysis"


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", _MODULE, *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_format_mermaid_is_rejected() -> None:
    result = _run("--edges", "T-001->T-002", "--format", "mermaid")
    assert result.returncode == 2
    assert "mermaid" in (result.stderr + result.stdout).lower()


def test_format_json_emits_analysis() -> None:
    result = _run("--edges", "T-001->T-002,T-002->T-003")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["cycle_detected"] is False
    assert data["topological_order"] == ["T-001", "T-002", "T-003"]
    assert data["critical_path"]


def test_cycle_exits_one() -> None:
    result = _run("--edges", "T-001->T-002,T-002->T-001")
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["cycle_detected"] is True
