"""``cataforge hook test`` and ``cataforge hook list`` smoke tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.main import cli


@pytest.fixture
def fresh_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from cataforge.core.scaffold import copy_scaffold_to

    copy_scaffold_to(tmp_path / ".cataforge", force=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _invoke(*args: str, input: str | None = None):
    runner = CliRunner()
    return runner.invoke(cli, list(args), input=input, catch_exceptions=False)


class TestHookList:
    def test_plain_list(self, fresh_project: Path) -> None:
        result = _invoke("hook", "list")
        assert result.exit_code == 0, result.output
        assert "PreToolUse" in result.output
        assert "guard_dangerous" in result.output

    def test_platform_flag_annotates_status(self, fresh_project: Path) -> None:
        result = _invoke("hook", "list", "--platform", "claude-code")
        assert result.exit_code == 0, result.output
        # Every built-in hook is native on claude-code.
        assert "[native]" in result.output


class TestHookTest:
    def test_block_hook_with_dangerous_command(self, fresh_project: Path) -> None:
        """guard_dangerous must exit 2 on rm -rf regardless of fixture plumbing."""
        payload = '{"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}'
        result = _invoke("hook", "test", "guard_dangerous", "--input", payload)
        assert result.exit_code == 2, result.output
        assert "BLOCKED" in result.output

    def test_block_hook_with_safe_command(self, fresh_project: Path) -> None:
        payload = '{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}'
        result = _invoke("hook", "test", "guard_dangerous", "--input", payload)
        assert result.exit_code == 0, result.output
        assert "OK" in result.output

    def test_unknown_hook_name(self, fresh_project: Path) -> None:
        result = _invoke("hook", "test", "nonexistent_hook_xyz", "--input", "{}")
        assert result.exit_code == 1
        assert "not declared" in result.output.lower() or "no hook" in result.output.lower()

    def test_invalid_json_payload(self, fresh_project: Path) -> None:
        result = _invoke("hook", "test", "guard_dangerous", "--input", "{not json")
        assert result.exit_code == 1
        assert "not valid JSON" in result.output


class TestHookCommandInterpreter:
    def test_resolved_command_pins_current_interpreter(self, fresh_project: Path) -> None:
        from cataforge.interface.cli.hook_cmd import _resolve_hook_command

        cmd = _resolve_hook_command(fresh_project, "guard_dangerous")

        quoted = f'"{Path(sys.executable).as_posix()}"'
        assert cmd == f"{quoted} -m cataforge.runtime.hook.scripts.guard_dangerous"

    def test_build_proc_invocation_maps_interpreter_to_argv(self, fresh_project: Path) -> None:
        from cataforge.interface.cli.hook_cmd import _build_proc_invocation

        quoted = f'"{Path(sys.executable).as_posix()}"'
        command = f"{quoted} -m cataforge.runtime.hook.scripts.guard_dangerous"

        proc_kwargs, _display = _build_proc_invocation(fresh_project, "guard_dangerous", command)

        assert proc_kwargs["shell"] is False
        args = proc_kwargs["args"]
        assert isinstance(args, list)
        assert args[0] == sys.executable
        assert args[1:] == ["-m", "cataforge.runtime.hook.scripts.guard_dangerous"]

    def test_interpreter_path_with_spaces_and_parens_routes_to_argv(
        self, fresh_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A quoted space/paren interpreter path must take the argv branch —
        the generic branch would reject the parens as shell metacharacters."""
        from cataforge.interface.cli.hook_cmd import (
            _build_proc_invocation,
            _resolve_hook_command,
        )

        fake = "C:/Program Files (x86)/uv tools/python.exe"
        monkeypatch.setattr(sys, "executable", fake)

        command = _resolve_hook_command(fresh_project, "guard_dangerous")
        assert command is not None
        proc_kwargs, _display = _build_proc_invocation(fresh_project, "guard_dangerous", command)

        assert proc_kwargs["shell"] is False
        args = proc_kwargs["args"]
        assert isinstance(args, list)
        assert args[0] == fake
        assert args[1:] == ["-m", "cataforge.runtime.hook.scripts.guard_dangerous"]
