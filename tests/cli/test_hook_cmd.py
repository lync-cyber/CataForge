"""``cataforge hook test`` and ``cataforge hook list`` smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli


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
        result = _invoke(
            "hook", "test", "guard_dangerous", "--input", payload
        )
        assert result.exit_code == 2, result.output
        assert "BLOCKED" in result.output

    def test_block_hook_with_safe_command(self, fresh_project: Path) -> None:
        payload = '{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}'
        result = _invoke(
            "hook", "test", "guard_dangerous", "--input", payload
        )
        assert result.exit_code == 0, result.output
        assert "OK" in result.output

    def test_unknown_hook_name(self, fresh_project: Path) -> None:
        result = _invoke("hook", "test", "nonexistent_hook_xyz", "--input", "{}")
        assert result.exit_code == 1
        assert "not declared" in result.output.lower() or "no hook" in result.output.lower()

    def test_invalid_json_payload(self, fresh_project: Path) -> None:
        result = _invoke(
            "hook", "test", "guard_dangerous", "--input", "{not json"
        )
        assert result.exit_code == 1
        assert "not valid JSON" in result.output
