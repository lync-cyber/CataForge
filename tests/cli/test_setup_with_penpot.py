"""`cataforge setup --with-penpot` enables the Penpot design integration.

The flag must set ``project.design_tool`` and write a declarative
``.cataforge/mcp/penpot.yaml`` so a later ``cataforge deploy`` injects the
Penpot MCP server. Without the flag neither artefact is created — the spec's
presence is the gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.setup_cmd import setup_command


def _framework(root: Path) -> dict:
    return json.loads((root / ".cataforge" / "framework.json").read_text(encoding="utf-8"))


def test_with_penpot_sets_design_tool_and_writes_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, ["--with-penpot"])
    assert result.exit_code == 0, result.output

    assert (_framework(tmp_path).get("project") or {}).get("design_tool") == "penpot"
    spec = tmp_path / ".cataforge" / "mcp" / "penpot.yaml"
    assert spec.is_file()
    body = spec.read_text(encoding="utf-8")
    assert "id: penpot" in body
    assert "/mcp/stream" in body


def test_without_penpot_leaves_design_tool_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, [])
    assert result.exit_code == 0, result.output

    assert (_framework(tmp_path).get("project") or {}).get("design_tool") == "none"
    assert not (tmp_path / ".cataforge" / "mcp" / "penpot.yaml").exists()


def test_with_penpot_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, ["--with-penpot", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "design_tool = penpot" in result.output
    assert not (tmp_path / ".cataforge").exists()
