"""detect_correction.py hook 行为测试 (On-Correction Learning 放宽)

覆盖:
  - option-override 命中: 用户选项 != (Recommended)
  - 无推荐时不记录
  - 用户接受推荐不记录
  - 非 AskUserQuestion 工具调用不记录
  - CORRECTIONS-LOG.md 追加写入而非覆盖
  - EVENT-LOG.jsonl 含 correction 条目
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK_SOURCE = os.path.join(PROJECT_ROOT, ".claude", "hooks", "detect_correction.py")


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """构造最小伪项目: 拷贝 hook + event_logger + phase_reader + 空 CLAUDE.md。"""
    (tmp_path / "docs" / "reviews").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "scripts").mkdir(parents=True)

    shutil.copy(HOOK_SOURCE, tmp_path / ".claude" / "hooks" / "detect_correction.py")
    for name in ("event_logger.py", "phase_reader.py"):
        shutil.copy(
            os.path.join(PROJECT_ROOT, ".claude", "scripts", name),
            tmp_path / ".claude" / "scripts" / name,
        )

    (tmp_path / "CLAUDE.md").write_text(
        "# Test\n## 项目状态\n- 当前阶段: architecture\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run_hook(tmp_project, payload: dict) -> subprocess.CompletedProcess:
    hook = tmp_project / ".claude" / "hooks" / "detect_correction.py"
    env = os.environ.copy()
    # Strip inherited env that could redirect the log back to the real repo.
    env.pop("CATAFORGE_EVENT_LOG", None)
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        cwd=str(tmp_project),
        env=env,
    )


def _read_events(tmp_project) -> list[dict]:
    log = tmp_project / "docs" / "EVENT-LOG.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _corrections_content(tmp_project) -> str:
    log = tmp_project / "docs" / "reviews" / "CORRECTIONS-LOG.md"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def _payload(question: str, options: list[dict], chosen: str) -> dict:
    return {
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": [{"question": question, "options": options}]},
        "tool_response": {"answers": {question: chosen}},
    }


# ============================================================================
# Positive: 命中 option-override
# ============================================================================


class TestOptionOverrideDetection:
    def test_override_triggers_correction(self, tmp_project):
        payload = _payload(
            "使用哪个数据库?",
            [
                {"label": "PostgreSQL (Recommended)", "description": "成熟稳定"},
                {"label": "MongoDB", "description": "文档型"},
            ],
            chosen="MongoDB",
        )
        result = _run_hook(tmp_project, payload)
        assert result.returncode == 0, result.stderr

        events = _read_events(tmp_project)
        assert len(events) == 1
        assert events[0]["event"] == "correction"
        assert "option-override" in events[0]["detail"]
        assert "MongoDB" in events[0]["detail"]

        log_content = _corrections_content(tmp_project)
        assert "option-override" in log_content
        assert "使用哪个数据库?" in log_content
        assert "PostgreSQL (Recommended)" in log_content
        assert "MongoDB" in log_content

    def test_chinese_recommended_label(self, tmp_project):
        """兼容 '(推荐)' 标记。"""
        payload = _payload(
            "前端框架?",
            [
                {"label": "React (推荐)", "description": "生态好"},
                {"label": "Vue", "description": "上手快"},
            ],
            chosen="Vue",
        )
        _run_hook(tmp_project, payload)
        events = _read_events(tmp_project)
        assert len(events) == 1
        assert events[0]["event"] == "correction"

    def test_appends_to_existing_log(self, tmp_project):
        """第二次命中应追加而非覆盖。"""
        for chosen in ("A", "B"):
            payload = _payload(
                f"Q-{chosen}",
                [
                    {"label": "X (Recommended)", "description": "d1"},
                    {"label": chosen, "description": "d2"},
                ],
                chosen=chosen,
            )
            _run_hook(tmp_project, payload)

        events = _read_events(tmp_project)
        assert len(events) == 2

        log_content = _corrections_content(tmp_project)
        assert "Q-A" in log_content
        assert "Q-B" in log_content


# ============================================================================
# Negative: 不应触发
# ============================================================================


class TestNoCorrection:
    def test_accept_recommended_no_event(self, tmp_project):
        payload = _payload(
            "Q",
            [
                {"label": "A (Recommended)", "description": "d1"},
                {"label": "B", "description": "d2"},
            ],
            chosen="A (Recommended)",
        )
        _run_hook(tmp_project, payload)
        assert _read_events(tmp_project) == []
        assert _corrections_content(tmp_project) == ""

    def test_no_recommended_label_no_event(self, tmp_project):
        """无 (Recommended) 基线时不记录，避免噪声。"""
        payload = _payload(
            "Q",
            [
                {"label": "A", "description": "d1"},
                {"label": "B", "description": "d2"},
            ],
            chosen="B",
        )
        _run_hook(tmp_project, payload)
        assert _read_events(tmp_project) == []

    def test_non_askuserquestion_tool_ignored(self, tmp_project):
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"stdout": ""},
        }
        result = _run_hook(tmp_project, payload)
        assert result.returncode == 0
        assert _read_events(tmp_project) == []

    def test_malformed_payload_exits_cleanly(self, tmp_project):
        """非 JSON 或缺字段不应崩溃。"""
        hook = tmp_project / ".claude" / "hooks" / "detect_correction.py"
        result = subprocess.run(
            [sys.executable, str(hook)],
            input="not json",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        assert result.returncode == 0
        assert _read_events(tmp_project) == []

    def test_empty_answers_no_event(self, tmp_project):
        payload = {
            "tool_name": "AskUserQuestion",
            "tool_input": {
                "questions": [
                    {
                        "question": "Q",
                        "options": [
                            {"label": "A (Recommended)", "description": "d"}
                        ],
                    }
                ]
            },
            "tool_response": {"answers": {}},
        }
        _run_hook(tmp_project, payload)
        assert _read_events(tmp_project) == []


# ============================================================================
# Multi-question
# ============================================================================


class TestMultiQuestion:
    def test_mixed_override_and_accept(self, tmp_project):
        """两个问题中只有一个命中 override，应只记录一条。"""
        payload = {
            "tool_name": "AskUserQuestion",
            "tool_input": {
                "questions": [
                    {
                        "question": "Q1",
                        "options": [
                            {"label": "A (Recommended)", "description": "d1"},
                            {"label": "B", "description": "d2"},
                        ],
                    },
                    {
                        "question": "Q2",
                        "options": [
                            {"label": "X (Recommended)", "description": "d3"},
                            {"label": "Y", "description": "d4"},
                        ],
                    },
                ]
            },
            "tool_response": {
                "answers": {"Q1": "A (Recommended)", "Q2": "Y"}
            },
        }
        _run_hook(tmp_project, payload)
        events = _read_events(tmp_project)
        assert len(events) == 1
        assert "Q2" in events[0]["detail"]
