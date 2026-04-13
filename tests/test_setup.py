"""setup.py 环境检测逻辑测试"""

import os
import sys


_scripts = os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts")
sys.path.insert(0, os.path.join(_scripts, "lib"))
sys.path.insert(0, os.path.join(_scripts, "framework"))
from setup import (
    check_project_dependencies,
    check_python,
    detect_node_pkg_manager,
    detect_python_pkg_manager,
)


# ── check_python ─────────────────────────────────────────────────────────


class TestCheckPython:
    def test_current_env_passes(self):
        """当前运行环境必然 >= 3.8"""
        assert check_python() is True


# ── detect_python_pkg_manager ────────────────────────────────────────────


class TestDetectPythonPkgManager:
    def test_uv_lock_detected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "uv.lock").write_text("")
        assert detect_python_pkg_manager() == "uv"

    def test_tool_uv_in_pyproject(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[tool.uv]\ndev-dependencies = []\n")
        assert detect_python_pkg_manager() == "uv"

    def test_no_markers_fallback_pip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No uv.lock, no [tool.uv], and mock uv away
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        import setup

        monkeypatch.setattr(setup, "has_command", lambda cmd: False)
        assert detect_python_pkg_manager() == "pip"


# ── detect_node_pkg_manager ─────────────────────────────────────────────


class TestDetectNodePkgManager:
    def test_pnpm_lock(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pnpm-lock.yaml").write_text("")
        assert detect_node_pkg_manager() == "pnpm"

    def test_yarn_lock(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "yarn.lock").write_text("")
        assert detect_node_pkg_manager() == "yarn"

    def test_bun_lock(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "bun.lockb").write_text("")
        assert detect_node_pkg_manager() == "bun"

    def test_default_npm(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert detect_node_pkg_manager() == "npm"


# ── check_project_dependencies ───────────────────────────────────────────


class TestCheckProjectDependencies:
    def test_no_deps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        suggestions = check_project_dependencies()
        assert len(suggestions) == 0

    def test_package_json_without_node_modules(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text('{"name": "test"}')
        suggestions = check_project_dependencies()
        assert any("install" in s for s in suggestions)

    def test_package_json_with_node_modules(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "node_modules").mkdir()
        suggestions = check_project_dependencies()
        assert not any("install" in s for s in suggestions)

    def test_requirements_txt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "requirements.txt").write_text("flask\nrequests\n")
        suggestions = check_project_dependencies()
        assert any("install" in s for s in suggestions)

    def test_pyproject_with_deps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = ["flask", "requests"]\n'
        )
        suggestions = check_project_dependencies()
        # 接受 pip install 或 uv sync，取决于环境
        assert any("install" in s or "sync" in s for s in suggestions)

    def test_pyproject_without_deps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = []\n'
        )
        suggestions = check_project_dependencies()
        # 空 dependencies 不应建议安装
        assert not any("install" in s or "sync" in s for s in suggestions)
