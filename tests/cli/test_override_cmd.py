"""Tests for ``cataforge override {list,eject}``."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.main import cli

_AGENT = """\
---
name: architect
---

# Role

## Identity
- base identity

## Execution Rules
- base rule
"""


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cf = tmp_path / ".cataforge"
    (cf / "agents" / "architect").mkdir(parents=True)
    (cf / "agents" / "architect" / "AGENT.md").write_text(_AGENT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_eject_whole_file_default_layer(runner: CliRunner, project: Path) -> None:
    result = runner.invoke(cli, ["override", "eject", "agents", "architect"])
    assert result.exit_code == 0, result.output
    dest = project / ".cataforge/overrides/project/agents/architect/AGENT.md"
    assert dest.is_file()
    assert "base identity" in dest.read_text(encoding="utf-8")


def test_eject_patch_with_section(runner: CliRunner, project: Path) -> None:
    result = runner.invoke(
        cli,
        [
            "override",
            "eject",
            "agents",
            "architect",
            "--patch",
            "--section",
            "Execution Rules",
            "--layer",
            "user",
        ],
    )
    assert result.exit_code == 0, result.output
    dest = project / ".cataforge/overrides/user/agents/architect/AGENT.patch.md"
    body = dest.read_text(encoding="utf-8")
    assert body.startswith("## Execution Rules")
    assert "base rule" in body


def test_eject_patch_unknown_section_errors(runner: CliRunner, project: Path) -> None:
    result = runner.invoke(
        cli,
        ["override", "eject", "agents", "architect", "--patch", "--section", "Nope"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_eject_refuses_clobber_without_force(runner: CliRunner, project: Path) -> None:
    runner.invoke(cli, ["override", "eject", "agents", "architect"])
    result = runner.invoke(cli, ["override", "eject", "agents", "architect"])
    assert result.exit_code != 0
    assert "exists" in result.output
    # --force allows it.
    ok = runner.invoke(cli, ["override", "eject", "agents", "architect", "--force"])
    assert ok.exit_code == 0, ok.output


def test_eject_unknown_asset_errors(runner: CliRunner, project: Path) -> None:
    result = runner.invoke(cli, ["override", "eject", "agents", "ghost"])
    assert result.exit_code != 0
    assert "no scaffold" in result.output


def test_list_shows_layers(runner: CliRunner, project: Path) -> None:
    runner.invoke(cli, ["override", "eject", "agents", "architect", "--layer", "user"])
    result = runner.invoke(cli, ["override", "list"])
    assert result.exit_code == 0, result.output
    assert "architect" in result.output
    # Defined in both scaffold and the user override layer.
    assert "scaffold" in result.output
    assert "user" in result.output
