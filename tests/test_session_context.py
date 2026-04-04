"""session_context.py 包管理器检测测试"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
from session_context import _detect_pkg_env


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
