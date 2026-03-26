"""guard_dangerous.py 危险命令拦截测试"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
from guard_dangerous import DANGEROUS_PATTERNS


def is_blocked(command: str) -> bool:
    """模拟 guard_dangerous.py 的检测逻辑"""
    for pattern, _, _ in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


# ── 应当拦截的命令 ───────────────────────────────────────────────────────


class TestBlocked:
    @pytest.mark.parametrize(
        "cmd",
        [
            "rm -rf /",
            "rm -rf .",
            "rm -rf node_modules",
            "rm -r somedir",
            "rmdir /s /q build",
            "del /s /q *.tmp",
            "format C:",
            "format D:",
            "git push --force",
            "git push origin main --force",
            "git reset --hard",
            "git reset --hard HEAD~1",
            "git clean -f",
            "git clean -fd",
        ],
    )
    def test_blocked(self, cmd):
        assert is_blocked(cmd), f"应当拦截但未拦截: {cmd}"


# ── 应当放行的命令 ───────────────────────────────────────────────────────


class TestAllowed:
    @pytest.mark.parametrize(
        "cmd",
        [
            "git status",
            "git log --oneline",
            "git diff",
            "git add .",
            "git commit -m 'test'",
            "git push",
            "git push origin main",
            "git push --force-with-lease",
            "git reset --soft HEAD~1",
            "ls -la",
            "npm install",
            "npm run build",
            "python -m pytest",
            "ruff check .",
        ],
    )
    def test_allowed(self, cmd):
        assert not is_blocked(cmd), f"不应拦截但被拦截: {cmd}"


# ── 边界情况 ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_force_with_lease_not_blocked(self):
        """--force-with-lease 是安全的 force push，应放行"""
        assert not is_blocked("git push --force-with-lease origin main")

    def test_force_push_blocked(self):
        """--force 应拦截"""
        assert is_blocked("git push --force origin main")
