"""session_context.py 去重行为测试

P0-1 后该 hook 仅保留 session_start 事件日志写入 + 60s 去重。
包管理器检测已迁移至 setup.py build_env_block（覆盖见 test_setup_env_block.py）。
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
from session_context import _should_log_session_start


class TestShouldLogSessionStart:
    def test_returns_true_when_no_log_file(self, tmp_path):
        assert _should_log_session_start(str(tmp_path)) is True

    def test_returns_true_when_no_session_start(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        log = docs / "EVENT-LOG.jsonl"
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": "phase_start"}
        log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        assert _should_log_session_start(str(tmp_path)) is True

    def test_returns_false_within_60s(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        log = docs / "EVENT-LOG.jsonl"
        recent_ts = datetime.now(timezone.utc).isoformat()
        entry = {"ts": recent_ts, "event": "session_start"}
        log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        assert _should_log_session_start(str(tmp_path)) is False

    def test_returns_true_after_60s(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        log = docs / "EVENT-LOG.jsonl"
        old_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        entry = {"ts": old_ts, "event": "session_start"}
        log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        assert _should_log_session_start(str(tmp_path)) is True


class TestHookSimplified:
    """P0-1 回归保护: hook 不应再包含环境检测或 additionalContext 注入。"""

    def test_no_additional_context_in_source(self):
        hook_file = os.path.join(
            os.path.dirname(__file__),
            "..",
            ".claude",
            "hooks",
            "session_context.py",
        )
        with open(hook_file, "r", encoding="utf-8") as f:
            source = f.read()
        assert "additionalContext" not in source, (
            "session_context.py 不应再注入 additionalContext（P0-1）"
        )
        assert "_detect_pkg_env" not in source, (
            "包管理器检测已迁移至 setup.py，hook 不应保留"
        )
