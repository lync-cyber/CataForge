"""L2 — 事件日志序列验证 (P0-3 Step 2)

目的: 针对 docs/EVENT-LOG.jsonl 的生成/追加/去重行为做结构化断言，
覆盖 orchestrator 在 hook / 手动 [EVENT] 调用下的实际控制流。

这不是语义 LLM 测试（那需要 SDK 集成层 L3）。本文件聚焦:
  - event_logger.append_event 写入格式符合 schema
  - session_context hook 在 60 秒内不会重复写 session_start
  - phase_reader 正确解析 CLAUDE.md 当前阶段

配合 L1 prompt 快照测试即可覆盖 80% 的控制流回归。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK_SCRIPT = os.path.join(PROJECT_ROOT, ".claude", "hooks", "session_context.py")


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """构造一个最小伪项目，含 docs/ 目录和空 CLAUDE.md。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "scripts").mkdir(parents=True)
    # 拷贝 session_context.py + event_logger.py + phase_reader.py
    import shutil

    for name in ("session_context.py",):
        shutil.copy(
            os.path.join(PROJECT_ROOT, ".claude", "hooks", name),
            tmp_path / ".claude" / "hooks" / name,
        )
    for name in ("event_logger.py", "phase_reader.py"):
        shutil.copy(
            os.path.join(PROJECT_ROOT, ".claude", "scripts", name),
            tmp_path / ".claude" / "scripts" / name,
        )
    (tmp_path / "CLAUDE.md").write_text(
        "# Test\n## 项目状态\n- 当前阶段: requirements\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _read_events(tmp_project) -> list[dict]:
    log = tmp_project / "docs" / "EVENT-LOG.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run_hook(tmp_project) -> subprocess.CompletedProcess:
    """以 echo '{}' 管道方式运行 session_context.py 模拟 SessionStart。"""
    hook_copy = tmp_project / ".claude" / "hooks" / "session_context.py"
    return subprocess.run(
        [sys.executable, str(hook_copy)],
        input="{}",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


def test_session_context_hook_writes_session_start(tmp_project) -> None:
    """首次运行 hook 必须写入一条 session_start 事件。"""
    result = _run_hook(tmp_project)
    assert result.returncode == 0, f"hook 失败: {result.stderr}"

    events = _read_events(tmp_project)
    assert len(events) == 1, f"期望 1 条事件，实际 {len(events)}"
    assert events[0]["event"] == "session_start"
    assert events[0]["phase"] == "requirements"


def test_session_context_hook_dedup_within_60s(tmp_project) -> None:
    """60 秒窗口内重复触发 hook 不应产生重复事件。"""
    _run_hook(tmp_project)
    _run_hook(tmp_project)
    _run_hook(tmp_project)

    events = _read_events(tmp_project)
    # 第 2、3 次调用应被去重
    session_starts = [e for e in events if e["event"] == "session_start"]
    assert len(session_starts) == 1, (
        f"去重失败: session_start 数量 = {len(session_starts)}"
    )


def test_session_context_hook_no_additional_context(tmp_project) -> None:
    """简化后的 hook 不再输出 additionalContext (P0-1 回归保护)。"""
    result = _run_hook(tmp_project)
    # stdout 应该为空或仅含无害调试（不应是 JSON 含 additionalContext）
    assert "additionalContext" not in result.stdout


def test_session_context_hook_respects_old_event_outside_window(
    tmp_project,
) -> None:
    """窗口外的旧事件不影响新写入。"""
    # 手动写一条 61 秒前的事件
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat()
    log = tmp_project / "docs" / "EVENT-LOG.jsonl"
    log.write_text(
        json.dumps(
            {
                "ts": old_ts,
                "event": "session_start",
                "phase": "requirements",
                "detail": "旧事件",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    _run_hook(tmp_project)

    events = _read_events(tmp_project)
    session_starts = [e for e in events if e["event"] == "session_start"]
    assert len(session_starts) == 2, "窗口外的新 session_start 应该被写入"
