"""`cataforge setup env-block` / `cataforge setup permissions` subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.main import cli


def _invoke(*args: str):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


def test_env_block_python_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup", "env-block")
    assert result.exit_code == 0, result.output
    assert "技术栈: python" in result.output
    assert "`uv sync`" in result.output


def test_env_block_no_stack_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".cataforge").mkdir()
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup", "env-block")
    assert result.exit_code == 2
    assert "无自动检测到的标准包管理器" in result.output


def test_permissions_narrows_claude_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("x", encoding="utf-8")
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup", "permissions")
    assert result.exit_code == 0, result.output
    allow = json.loads((claude / "settings.json").read_text(encoding="utf-8"))["permissions"][
        "allow"
    ]
    assert "Bash(uv *)" in allow
    assert "Bash(git *)" in allow


def test_permissions_no_stack_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".cataforge").mkdir()
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup", "permissions")
    assert result.exit_code == 2


def test_permissions_no_settings_file_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup", "permissions")
    assert result.exit_code == 1


def test_bare_setup_still_scaffolds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The group with invoke_without_command keeps `cataforge setup` initialising."""
    monkeypatch.chdir(tmp_path)
    result = _invoke("setup")
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".cataforge").is_dir()


def test_setup_check_prereqs_does_not_write_gitattributes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup", "--check-prereqs")

    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".gitattributes").exists()


def test_setup_gitattributes_writes_default_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup", "gitattributes")

    assert result.exit_code == 0, result.output
    assert "wrote .gitattributes" in result.output
    assert "* text=auto eol=lf" in (tmp_path / ".gitattributes").read_text(encoding="utf-8")


def test_setup_gitattributes_preserves_existing_and_fails_when_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = "*.txt text\n"
    (tmp_path / ".gitattributes").write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup", "gitattributes")

    assert result.exit_code == 1
    assert "preserving user-owned file" in result.output
    assert (tmp_path / ".gitattributes").read_text(encoding="utf-8") == original


def test_bare_setup_writes_gitattributes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = _invoke("setup")

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".gitattributes").is_file()
