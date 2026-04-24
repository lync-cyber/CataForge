"""Tests for detect_review_flag hook."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path


def _run_hook(project_root: Path, payload: dict) -> subprocess.CompletedProcess:
    """Invoke detect_review_flag as a subprocess with stdin JSON."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_root)}
    return subprocess.run(
        [sys.executable, "-m", "cataforge.hook.scripts.detect_review_flag"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=str(project_root),
        env=env,
        timeout=10,
    )


def _bootstrap_project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    return tmp_path


def _reviewer_report(severity: str = "CRITICAL", with_assumption: bool = True) -> str:
    body_assumption = "上游 [ASSUMPTION] " if with_assumption else ""
    return textwrap.dedent(f"""
        # REVIEW-arch-r1

        ### [R-001] {severity}: {body_assumption}选错了打包策略
        - **category**: design-choice
        - **root_cause**: self-caused
        - **描述**: {body_assumption}选了多包但实际只有一个发布单元
        - **建议**: 改回单仓库

        ### [R-002] LOW: 文档拼写
        - **category**: doc-quality
        - **root_cause**: self-caused
        - **描述**: 拼写错误若干
        - **建议**: 校对
    """).strip()


def test_review_flag_records_critical_assumption(tmp_path: Path) -> None:
    project = _bootstrap_project(tmp_path)
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "architect", "phase": "architecture"},
        "tool_response": _reviewer_report(severity="CRITICAL"),
    }

    proc = _run_hook(project, payload)
    assert proc.returncode == 0, proc.stderr.decode()

    log = project / "docs" / "reviews" / "CORRECTIONS-LOG.md"
    assert log.is_file(), proc.stderr.decode()
    text = log.read_text(encoding="utf-8")
    assert "review-flag" in text
    assert "[R-001]" in text
    assert "architect" in text
    # The LOW issue must NOT have been recorded.
    assert "[R-002]" not in text


def test_review_flag_ignores_report_without_assumption(tmp_path: Path) -> None:
    project = _bootstrap_project(tmp_path)
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "architect", "phase": "architecture"},
        "tool_response": _reviewer_report(severity="CRITICAL", with_assumption=False),
    }

    proc = _run_hook(project, payload)
    assert proc.returncode == 0, proc.stderr.decode()
    assert not (project / "docs" / "reviews" / "CORRECTIONS-LOG.md").exists()


def test_review_flag_ignores_medium_severity(tmp_path: Path) -> None:
    project = _bootstrap_project(tmp_path)
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "architect", "phase": "architecture"},
        "tool_response": _reviewer_report(severity="MEDIUM"),
    }

    proc = _run_hook(project, payload)
    assert proc.returncode == 0, proc.stderr.decode()
    assert not (project / "docs" / "reviews" / "CORRECTIONS-LOG.md").exists()


def test_review_flag_ignores_non_agent_tool(tmp_path: Path) -> None:
    project = _bootstrap_project(tmp_path)
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_response": _reviewer_report(),
    }

    proc = _run_hook(project, payload)
    assert proc.returncode == 0
    assert not (project / "docs" / "reviews" / "CORRECTIONS-LOG.md").exists()
