"""Characterization: sprint_check.main blocking early-exit emit.

main() had no end-to-end coverage; these lock the two blocking early exits —
dev_plan_missing and sprint_tasks_missing — across text and JSON, pinning the
single-issue payload shape that the emit helper must reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.runtime.skill.builtins.sprint_review import sprint_check


@pytest.fixture(autouse=True)
def _no_utf8_relaunch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sprint_check, "ensure_utf8", lambda: None)


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["sprint_check", *argv])
    sprint_check.main()


def test_main_dev_plan_missing_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as exc:
        _run(["1", "--dev-plan", str(missing)], monkeypatch)
    assert exc.value.code == 1
    assert capsys.readouterr().out.strip() == f"[CRITICAL] 未找到dev-plan文件: {missing}"


def test_main_dev_plan_missing_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as exc:
        _run(["2", "--dev-plan", str(missing), "--format", "json"], monkeypatch)
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out) == {
        "sprint": 2,
        "summary": {"blocking": 1, "advisory": 0, "total": 1},
        "issues": [
            {
                "severity": "CRITICAL",
                "category": "dev_plan_missing",
                "message": f"未找到dev-plan文件: {missing}",
            }
        ],
    }


def test_main_sprint_tasks_missing_json_carries_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dp = tmp_path / "dev-plan"
    dp.mkdir()
    (dp / "dev-plan.md").write_text(
        "---\nid: dev-plan\n---\n## 1. Overview\nno sprint anchor here\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        _run(["7", "--dev-plan", str(dp), "--format", "json"], monkeypatch)
    assert exc.value.code == 1
    issue = json.loads(capsys.readouterr().out)["issues"][0]
    assert issue["category"] == "sprint_tasks_missing"
    assert issue["reason"] in sprint_check._EMPTY_EXTRACTION_MESSAGES
    assert issue["message"] == sprint_check._EMPTY_EXTRACTION_MESSAGES[issue["reason"]].format(
        sprint=7
    )
