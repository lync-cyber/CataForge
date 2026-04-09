"""log_agent_dispatch.py PreToolUse hook tests"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
from log_agent_dispatch import _extract_task_type


class TestExtractTaskType:
    def test_extracts_new_creation(self):
        prompt = "任务类型: new_creation\n执行架构设计"
        assert _extract_task_type(prompt) == "new_creation"

    def test_extracts_revision(self):
        prompt = "任务类型: revision\n修订文档"
        assert _extract_task_type(prompt) == "revision"

    def test_extracts_continuation(self):
        prompt = "任务类型: continuation\n恢复执行"
        assert _extract_task_type(prompt) == "continuation"

    def test_returns_none_for_no_match(self):
        assert _extract_task_type("普通prompt没有任务类型") is None

    def test_returns_none_for_empty(self):
        assert _extract_task_type("") is None

    def test_returns_none_for_none(self):
        assert _extract_task_type(None) is None

    def test_extracts_amendment(self):
        prompt = "任务类型: amendment\n变更修订"
        assert _extract_task_type(prompt) == "amendment"

    def test_task_type_with_extra_spaces(self):
        prompt = "任务类型:   new_creation  \n其他内容"
        assert _extract_task_type(prompt) == "new_creation"
