"""setup.py 环境检测逻辑测试"""

import os
import sys
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "scripts"))
from setup import check_project_dependencies, check_python


def _quiet(func, *args, **kwargs):
    """运行函数并静默其 stdout 输出。"""
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        return func(*args, **kwargs)
    finally:
        sys.stdout = old_stdout


# ── check_python ─────────────────────────────────────────────────────────


class TestCheckPython:
    def test_current_env_passes(self):
        """当前运行环境必然 >= 3.8"""
        assert _quiet(check_python) is True


# ── check_project_dependencies ───────────────────────────────────────────


class TestCheckProjectDependencies:
    def test_no_deps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        suggestions = _quiet(check_project_dependencies)
        assert len(suggestions) == 0

    def test_package_json_without_node_modules(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text('{"name": "test"}')
        suggestions = _quiet(check_project_dependencies)
        assert "npm install" in suggestions

    def test_package_json_with_node_modules(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "node_modules").mkdir()
        suggestions = _quiet(check_project_dependencies)
        assert "npm install" not in suggestions

    def test_requirements_txt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "requirements.txt").write_text("flask\nrequests\n")
        suggestions = _quiet(check_project_dependencies)
        assert any("pip install" in s for s in suggestions)

    def test_pyproject_with_deps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = ["flask", "requests"]\n'
        )
        suggestions = _quiet(check_project_dependencies)
        assert any("pip install" in s for s in suggestions)

    def test_pyproject_without_deps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = []\n'
        )
        suggestions = _quiet(check_project_dependencies)
        # 空 dependencies 不应建议安装
        assert not any("pip install -e" in s for s in suggestions)
