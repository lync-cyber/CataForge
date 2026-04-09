"""session_context.py 包管理器检测 + session_start 去重测试"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
from session_context import _detect_pkg_env, _should_log_session_start


class TestDetectPkgEnvPython:
    def test_uv_lock_detected(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        (tmp_path / "uv.lock").write_text("")
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Python pkg-manager: uv" in result

    def test_tool_uv_in_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.uv]\ndev-dependencies = []\n")
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Python pkg-manager: uv" in result

    def test_pip_fallback(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask\n")
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Python pkg-manager: pip" in result

    def test_uv_command_available(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        result = _detect_pkg_env(str(tmp_path), lambda cmd: cmd == "uv")
        assert "Python pkg-manager: uv" in result


class TestDetectPkgEnvNode:
    def test_npm_default(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "x"}')
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Node pkg-manager: npm" in result

    def test_yarn_lock(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "x"}')
        (tmp_path / "yarn.lock").write_text("")
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Node pkg-manager: yarn" in result

    def test_pnpm_lock(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "x"}')
        (tmp_path / "pnpm-lock.yaml").write_text("")
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Node pkg-manager: pnpm" in result

    def test_bun_lock(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "x"}')
        (tmp_path / "bun.lockb").write_text("")
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Node pkg-manager: bun" in result


class TestDetectPkgEnvOther:
    def test_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/foo\n")
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Go modules detected" in result

    def test_dotnet_csproj(self, tmp_path):
        (tmp_path / "App.csproj").write_text("<Project/>")
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "dotnet detected" in result

    def test_empty_project(self, tmp_path):
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert result == ""

    def test_consistency_warning(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "x"}')
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Do NOT mix" in result


class TestDetectPkgEnvMultiStack:
    def test_python_and_node(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        (tmp_path / "package.json").write_text('{"name": "x"}')
        result = _detect_pkg_env(str(tmp_path), lambda cmd: False)
        assert "Python pkg-manager:" in result
        assert "Node pkg-manager:" in result


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
