"""sprint-review task extraction — deterministic sprint→task attribution.

The overview table under a ``### Sprint N`` heading is the authoritative
membership map. A row whose first cell is a task id counts as a sprint task
even when the table carries no status column (status is then backfilled or
treated as externally tracked). Attribution never leaks across files, and a
task seen in both the overview and its detail card collapses to one entry.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cataforge.runtime.skill.builtins.sprint_review._extract import (
    classify_empty_extraction,
    extract_sprint_tasks,
)


def _write(tmp_path: Path, files: dict[str, str]) -> list[str]:
    paths: list[str] = []
    for name, content in files.items():
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        paths.append(str(p))
    return sorted(paths)


_OVERVIEW_NO_STATUS = (
    "## 1. 迭代规划\n"
    "### Sprint 4: 主题\n"
    "| 任务 | 标题 | 模块 | 复杂度 | task_kind | tdd_mode | 依赖 |\n"
    "|---|---|---|---|---|---|---|\n"
    "| T-040 | a | M-004 | M | feature | light | — |\n"
    "| T-041 | b | M-004 | L | feature | standard | T-040 |\n"
)


class TestNoStatusOverview:
    def test_rows_without_status_column_are_captured(self, tmp_path: Path) -> None:
        """A ``### Sprint N`` overview table without a status column still
        yields its task rows — the row's first cell is the membership signal."""
        files = _write(
            tmp_path,
            {
                "dev-plan-x.md": _OVERVIEW_NO_STATUS,
                "dev-plan-x-tasks-s1s5.md": (
                    "## 3. 任务卡详细\n"
                    "### T-040: a\n- deliverables:\n  - src/a.py\n"
                    "### T-041: b\n- deliverables:\n  - src/b.py\n"
                ),
            },
        )
        tasks = extract_sprint_tasks(files, 4)
        assert sorted(t["id"] for t in tasks) == ["T-040", "T-041"]
        assert all(t["status"] == "" for t in tasks)

    def test_status_column_still_captured_when_present(self, tmp_path: Path) -> None:
        files = _write(
            tmp_path,
            {
                "dev-plan-x.md": (
                    "### Sprint 1: t\n| 任务ID | 名 | 状态 |\n|---|---|---|\n| T-001 | a | done |\n"
                ),
            },
        )
        tasks = extract_sprint_tasks(files, 1)
        assert len(tasks) == 1
        assert tasks[0]["status"] == "done"


class TestDeduplication:
    def test_overview_row_and_card_collapse_to_one(self, tmp_path: Path) -> None:
        """A single-file dev-plan listing a task in the §1 overview and again
        as a §3 card must not double-count it."""
        files = _write(
            tmp_path,
            {
                "dev-plan-x.md": (
                    "## 1. 迭代规划\n"
                    "### Sprint 1: t\n"
                    "| 任务ID | 名 | 状态 |\n|---|---|---|\n"
                    "| T-001 | a | done |\n"
                    "\n## 3. 任务卡详细\n"
                    "### T-001: a\n- status: done\n- deliverables:\n  - src/a.py\n"
                ),
            },
        )
        tasks = extract_sprint_tasks(files, 1)
        assert [t["id"] for t in tasks] == ["T-001"]
        assert tasks[0]["status"] == "done"
        assert "src/a.py" in tasks[0]["deliverables"]


class TestNoCrossFileLeak:
    def test_in_sprint_does_not_leak_into_other_files(self, tmp_path: Path) -> None:
        """A ``### Sprint 4`` heading in one file must not attribute a card
        that lives in another file with no sprint heading of its own."""
        files = _write(
            tmp_path,
            {
                "dev-plan-a.md": (
                    "### Sprint 4: t\n| 任务 | 名 | 模块 |\n|---|---|---|\n| T-040 | a | M-004 |\n"
                ),
                "dev-plan-b.md": (
                    "## 3. 任务卡详细\n### T-099: later\n- deliverables:\n  - src/z.py\n"
                ),
            },
        )
        tasks = extract_sprint_tasks(files, 4)
        assert "T-099" not in [t["id"] for t in tasks]
        assert [t["id"] for t in tasks] == ["T-040"]


class TestNoSprintSuffixVolume:
    def test_s_suffix_file_needs_heading_to_scope_tasks(self, tmp_path: Path) -> None:
        """A ``-s{N}.md``-named file is not special: sprint membership comes
        only from a ``### Sprint N`` heading, never from the filename."""
        files = _write(
            tmp_path,
            {
                "dev-plan-x-s4.md": (
                    "## 3. 任务卡详细\n### T-040: a\n- deliverables:\n  - src/a.py\n"
                ),
            },
        )
        # No `### Sprint 4` heading anywhere → no tasks attributed to sprint 4.
        assert extract_sprint_tasks(files, 4) == []


class TestClassifyEmptyExtraction:
    def test_no_anchor_for_sprint(self, tmp_path: Path) -> None:
        """Sprint with no ``### Sprint N`` heading — a layout/anchor miss,
        not a genuinely empty sprint."""
        files = _write(
            tmp_path,
            {"dev-plan-x.md": _OVERVIEW_NO_STATUS},  # only Sprint 4 anchored
        )
        reason = classify_empty_extraction(files, 7)
        assert reason == "no_anchor"

    def test_anchored_but_empty(self, tmp_path: Path) -> None:
        """Sprint anchored (heading present) yet its section exposes no task
        rows, while other sprints do define tasks — not a 'no tasks' dev-plan."""
        files = _write(
            tmp_path,
            {
                "dev-plan-x.md": (
                    "### Sprint 1: t\n"
                    "| 任务 | 名 |\n|---|---|\n| T-001 | a |\n"
                    "\n### Sprint 4: later\n"
                    "| 阶段 | 说明 |\n|---|---|\n| 设计 | x |\n"
                ),
            },
        )
        reason = classify_empty_extraction(files, 4)
        assert reason == "anchored_empty"

    def test_genuinely_empty_dev_plan(self, tmp_path: Path) -> None:
        files = _write(tmp_path, {"dev-plan-x.md": "# Plan\n\nNo tasks yet.\n"})
        assert classify_empty_extraction(files, 1) == "no_tasks"


class TestEmptyExtractionCli:
    def test_no_anchor_reason_surfaces_in_json(self, tmp_path: Path) -> None:
        """The CLI replaces the blanket '未找到任务' with the classified reason
        so a layout miss is distinguishable from a genuinely empty sprint."""
        devdir = tmp_path / "docs" / "dev-plan"
        devdir.mkdir(parents=True)
        (devdir / "dev-plan-x.md").write_text(_OVERVIEW_NO_STATUS, encoding="utf-8")

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "cataforge.runtime.skill.builtins.sprint_review.sprint_check",
                "7",  # only Sprint 4 is anchored
                "--dev-plan",
                str(devdir),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        assert proc.returncode == 1, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["issues"][0]["reason"] == "no_anchor"
