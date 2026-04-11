"""setup.py build_env_block + 最小 permissions 生成 测试 (P0-1 + P2-1)"""

import json
import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP_PY = os.path.join(PROJECT_ROOT, ".claude", "scripts", "setup.py")

sys.path.insert(0, os.path.join(PROJECT_ROOT, ".claude", "scripts"))
from setup import (  # noqa: E402
    FRAMEWORK_CORE_PERMISSIONS,
    build_env_block,
    build_minimal_allow_list,
    detect_active_stacks,
)


class TestBuildEnvBlock:
    def test_empty_project_returns_empty(self, tmp_path):
        assert build_env_block(str(tmp_path)) == ""

    def test_python_uv_via_lock(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n')
        (tmp_path / "uv.lock").write_text("")
        block = build_env_block(str(tmp_path))
        assert "Python" in block
        assert "uv sync" in block
        assert "uv run python -m pytest" in block

    def test_python_pip_fallback(self, tmp_path, monkeypatch):
        (tmp_path / "requirements.txt").write_text("flask\n")
        # 强制 has_command("uv") -> False
        monkeypatch.setattr("setup.has_command", lambda name: False)
        block = build_env_block(str(tmp_path))
        assert "Python" in block
        assert "pip install -e ." in block

    def test_node_pnpm(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name":"x"}')
        (tmp_path / "pnpm-lock.yaml").write_text("")
        block = build_env_block(str(tmp_path))
        assert "Node" in block
        assert "pnpm install" in block
        assert "pnpm exec" in block

    def test_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/x\n")
        block = build_env_block(str(tmp_path))
        assert "Go" in block
        assert "go test ./..." in block

    def test_dotnet(self, tmp_path):
        (tmp_path / "App.csproj").write_text("<Project/>")
        block = build_env_block(str(tmp_path))
        assert ".NET" in block
        assert "dotnet test" in block

    def test_constraint_footer_included(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n')
        block = build_env_block(str(tmp_path))
        assert "不混用" in block


class TestEmitEnvBlockSubcommand:
    def test_exit_2_on_empty(self, tmp_path):
        result = subprocess.run(
            [sys.executable, SETUP_PY, "--emit-env-block"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 2

    def test_exit_0_with_stdout(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x\n")
        result = subprocess.run(
            [sys.executable, SETUP_PY, "--emit-env-block"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0
        assert "Go" in result.stdout


class TestDetectActiveStacks:
    def test_empty(self, tmp_path):
        assert detect_active_stacks(str(tmp_path)) == []

    def test_python_uv(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n')
        (tmp_path / "uv.lock").write_text("")
        assert "python-uv" in detect_active_stacks(str(tmp_path))

    def test_multi_stack(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n')
        (tmp_path / "uv.lock").write_text("")
        (tmp_path / "package.json").write_text('{"name":"x"}')
        (tmp_path / "go.mod").write_text("module x\n")
        stacks = detect_active_stacks(str(tmp_path))
        assert "python-uv" in stacks
        assert "node-npm" in stacks
        assert "go" in stacks


class TestBuildMinimalAllowList:
    def test_framework_core_always_included(self, tmp_path):
        allow = build_minimal_allow_list(str(tmp_path))
        for core in FRAMEWORK_CORE_PERMISSIONS:
            assert core in allow

    def test_no_stack_specific_for_empty(self, tmp_path):
        allow = build_minimal_allow_list(str(tmp_path))
        # 空项目不应包含任何 stack 特定规则
        assert not any("uv " in a for a in allow)
        assert not any("npm " in a for a in allow)
        assert not any("go mod" in a for a in allow)

    def test_python_uv_project(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n')
        (tmp_path / "uv.lock").write_text("")
        allow = build_minimal_allow_list(str(tmp_path))
        assert any("uv sync" in a for a in allow)
        assert any("uv run" in a for a in allow)
        # 不应包含 Node/Go 特定条目
        assert not any("npm " in a for a in allow)

    def test_deduplication(self, tmp_path):
        # 触发多个栈使 FRAMEWORK_CORE 可能重复
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n')
        (tmp_path / "uv.lock").write_text("")
        allow = build_minimal_allow_list(str(tmp_path))
        assert len(allow) == len(set(allow)), "allow 列表必须去重"


class TestEmitPermissionsSubcommand:
    def test_outputs_json_array(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x\n")
        result = subprocess.run(
            [sys.executable, SETUP_PY, "--emit-permissions"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, list)
        assert any("go test" in item for item in parsed)


class TestApplyPermissionsSubcommand:
    def test_rewrites_settings_allow(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        # 伪造一个含多余规则的 settings.json
        initial = {
            "permissions": {
                "allow": [
                    "Bash(npm install*)",
                    "Bash(uv sync*)",
                    "Bash(go mod *)",
                    "Bash(dotnet test*)",
                ],
                "deny": ["Bash(rm -rf *)"],
            }
        }
        (claude_dir / "settings.json").write_text(
            json.dumps(initial, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 只有 Python uv 项目
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n')
        (tmp_path / "uv.lock").write_text("")

        result = subprocess.run(
            [sys.executable, SETUP_PY, "--apply-permissions"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stderr

        written = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        allow = written["permissions"]["allow"]
        # Node/Go/.NET 条目应被移除
        assert not any("npm install" in a for a in allow)
        assert not any("go mod " in a for a in allow)
        assert not any("dotnet test" in a for a in allow)
        # Python uv 条目应保留
        assert any("uv sync" in a for a in allow)
        # deny 不变
        assert written["permissions"]["deny"] == ["Bash(rm -rf *)"]
