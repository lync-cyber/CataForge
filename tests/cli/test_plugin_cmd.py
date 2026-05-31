"""Tests for ``cataforge plugin {install,remove}`` (P3)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from cataforge.interface.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".cataforge").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _src_plugin(base: Path, plugin_id: str) -> Path:
    src = base / "src" / plugin_id
    (src / "skills" / "greet").mkdir(parents=True)
    (src / "cataforge-plugin.yaml").write_text(
        yaml.safe_dump({"id": plugin_id, "provides": {"skills": ["greet"]}}),
        encoding="utf-8",
    )
    (src / "skills" / "greet" / "SKILL.md").write_text(
        "---\nname: greet\n---\nbody\n", encoding="utf-8"
    )
    return src


def test_install_local_dir_copies(runner: CliRunner, project: Path) -> None:
    src = _src_plugin(project, "demo")
    result = runner.invoke(cli, ["plugin", "install", str(src)])
    assert result.exit_code == 0, result.output
    dest = project / ".cataforge" / "plugins" / "demo"
    assert (dest / "cataforge-plugin.yaml").is_file()
    assert (dest / "skills" / "greet" / "SKILL.md").is_file()
    assert "installed local plugin 'demo'" in result.output


def test_install_refuses_clobber_without_force(runner: CliRunner, project: Path) -> None:
    src = _src_plugin(project, "demo")
    runner.invoke(cli, ["plugin", "install", str(src)])
    again = runner.invoke(cli, ["plugin", "install", str(src)])
    assert again.exit_code != 0
    assert "already installed" in again.output
    forced = runner.invoke(cli, ["plugin", "install", str(src), "--force"])
    assert forced.exit_code == 0, forced.output


def test_install_non_plugin_dir_errors(runner: CliRunner, project: Path) -> None:
    plain = project / "plain"
    plain.mkdir()
    result = runner.invoke(cli, ["plugin", "install", str(plain)])
    assert result.exit_code != 0
    assert "no cataforge-plugin.yaml" in result.output


def test_install_pip_path_invokes_pip(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "cataforge.interface.cli.plugin_cmd._pip", lambda args: calls.append(args)
    )
    result = runner.invoke(cli, ["plugin", "install", "cataforge-some-plugin"])
    assert result.exit_code == 0, result.output
    assert calls == [["install", "cataforge-some-plugin"]]


def test_remove_local_dir(runner: CliRunner, project: Path) -> None:
    src = _src_plugin(project, "demo")
    runner.invoke(cli, ["plugin", "install", str(src)])
    result = runner.invoke(cli, ["plugin", "remove", "demo"])
    assert result.exit_code == 0, result.output
    assert not (project / ".cataforge" / "plugins" / "demo").exists()


def test_remove_pip_path_invokes_pip(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "cataforge.interface.cli.plugin_cmd._pip", lambda args: calls.append(args)
    )
    result = runner.invoke(cli, ["plugin", "remove", "cataforge-some-plugin"])
    assert result.exit_code == 0, result.output
    assert calls == [["uninstall", "-y", "cataforge-some-plugin"]]
