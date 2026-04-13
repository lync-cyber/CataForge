"""upgrade.py 自升级 re-exec 行为测试 (P0-2)"""

import hashlib
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts"))
import _upgrade_remote as upgrade  # noqa: E402


def _mkscript(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestFileSha256:
    def test_missing_file(self, tmp_path):
        assert upgrade._file_sha256(str(tmp_path / "nope.py")) == ""

    def test_returns_sha256(self, tmp_path):
        p = tmp_path / "x.py"
        p.write_text("hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert upgrade._file_sha256(str(p)) == expected

    def test_different_content_different_hash(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("print(1)")
        b.write_text("print(2)")
        assert upgrade._file_sha256(str(a)) != upgrade._file_sha256(str(b))


class TestMaybeSelfReexec:
    def test_skip_when_marker_set(self, tmp_path, monkeypatch):
        """第二阶段（marker 已设置）必须跳过自升级检测。"""
        monkeypatch.setenv(upgrade.SELF_UPGRADE_MARKER, "1")
        execve = mock.MagicMock()
        monkeypatch.setattr(os, "execve", execve)

        upgrade.maybe_self_reexec(str(tmp_path), dry_run=False)
        execve.assert_not_called()

    def test_skip_when_new_script_missing(self, tmp_path, monkeypatch):
        """新版本未包含 upgrade.py 时应跳过。"""
        monkeypatch.delenv(upgrade.SELF_UPGRADE_MARKER, raising=False)
        execve = mock.MagicMock()
        monkeypatch.setattr(os, "execve", execve)

        upgrade.maybe_self_reexec(str(tmp_path), dry_run=False)
        execve.assert_not_called()

    def test_skip_when_hashes_equal(self, tmp_path, monkeypatch):
        """新旧 upgrade.py 内容相同时不触发 exec。"""
        monkeypatch.delenv(upgrade.SELF_UPGRADE_MARKER, raising=False)

        content = "print('same')\n"
        new_script = tmp_path / ".claude" / "scripts" / "upgrade.py"
        _mkscript(str(new_script), content)

        cur_script = tmp_path / "cur_upgrade.py"
        cur_script.write_text(content)
        monkeypatch.setattr(sys, "argv", [str(cur_script)])

        execve = mock.MagicMock()
        monkeypatch.setattr(os, "execve", execve)

        upgrade.maybe_self_reexec(str(tmp_path), dry_run=False)
        execve.assert_not_called()

    def test_triggers_execve_when_hashes_differ(self, tmp_path, monkeypatch):
        """新旧 upgrade.py 内容不同时，应调用 os.execve 切换进程。"""
        monkeypatch.delenv(upgrade.SELF_UPGRADE_MARKER, raising=False)
        monkeypatch.delenv(upgrade.SELF_UPGRADE_SRC_ENV, raising=False)

        new_script = tmp_path / ".claude" / "scripts" / "upgrade.py"
        _mkscript(str(new_script), "print('new version')\n")

        cur_script = tmp_path / "cur_upgrade.py"
        cur_script.write_text("print('old version')\n")
        monkeypatch.setattr(sys, "argv", [str(cur_script)])

        execve = mock.MagicMock()
        monkeypatch.setattr(os, "execve", execve)

        upgrade.maybe_self_reexec(str(tmp_path), dry_run=False)
        execve.assert_called_once()
        call = execve.call_args
        # 参数 1: python interpreter
        assert call.args[0] == sys.executable
        # 参数 2: argv 列表
        argv = call.args[1]
        assert argv[0] == sys.executable
        assert argv[1] == str(new_script)
        assert argv[2] == "local"
        assert argv[3] == str(tmp_path)
        # 参数 3: env 必须含 marker 和 src
        env = call.args[2]
        assert env[upgrade.SELF_UPGRADE_MARKER] == "1"
        assert env[upgrade.SELF_UPGRADE_SRC_ENV] == str(tmp_path)

    def test_dry_run_flag_propagated(self, tmp_path, monkeypatch):
        monkeypatch.delenv(upgrade.SELF_UPGRADE_MARKER, raising=False)

        new_script = tmp_path / ".claude" / "scripts" / "upgrade.py"
        _mkscript(str(new_script), "print('new')\n")

        cur_script = tmp_path / "cur_upgrade.py"
        cur_script.write_text("print('old')\n")
        monkeypatch.setattr(sys, "argv", [str(cur_script)])

        execve = mock.MagicMock()
        monkeypatch.setattr(os, "execve", execve)

        upgrade.maybe_self_reexec(str(tmp_path), dry_run=True)
        argv = execve.call_args.args[1]
        assert "--dry-run" in argv

    def test_execve_failure_falls_through(self, tmp_path, monkeypatch):
        """os.execve 抛 OSError 时不应崩溃，而是回退到当前脚本继续。"""
        monkeypatch.delenv(upgrade.SELF_UPGRADE_MARKER, raising=False)

        new_script = tmp_path / ".claude" / "scripts" / "upgrade.py"
        _mkscript(str(new_script), "print('new')\n")
        cur_script = tmp_path / "cur.py"
        cur_script.write_text("print('old')\n")
        monkeypatch.setattr(sys, "argv", [str(cur_script)])

        monkeypatch.setattr(
            os, "execve", mock.MagicMock(side_effect=OSError("mock failure"))
        )

        # 不应抛出
        upgrade.maybe_self_reexec(str(tmp_path), dry_run=False)
