"""`cataforge setup --context-mode` selects the context source-of-truth mode.

Couples with the markdown KG-bypass: selecting markdown must both persist
``context.mode`` and make ``kg_enabled`` report False.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.setup import _flow, setup_command


def _mode(root: Path) -> str:
    data = json.loads((root / ".cataforge" / "framework.json").read_text(encoding="utf-8"))
    return (data.get("context") or {}).get("mode")


def test_flag_markdown_persists_and_disables_kg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache, kg_enabled

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, ["--context-mode", "markdown"])
    assert result.exit_code == 0, result.output
    assert _mode(tmp_path) == "markdown"

    invalidate_cache()
    assert kg_enabled(tmp_path) is False
    invalidate_cache()


def test_flag_graph_persists_and_enables_kg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache, kg_enabled

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, ["--context-mode", "graph"])
    assert result.exit_code == 0, result.output
    assert _mode(tmp_path) == "graph"

    invalidate_cache()
    assert kg_enabled(tmp_path) is True
    invalidate_cache()


def test_non_interactive_defaults_to_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No flag + no TTY → scaffold default (graph) is untouched, no prompt."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, [])
    assert result.exit_code == 0, result.output
    assert _mode(tmp_path) == "graph"


def test_interactive_prompt_selects_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh interactive install with no flag prompts; choosing markdown."""
    import click

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(_flow, "_prompt_context_mode", lambda: "markdown")

    # The setup group callback reads the active context's invoked_subcommand;
    # drive it under a real context (no subcommand → init path runs).
    ctx = click.Context(setup_command)
    with ctx:
        setup_command.callback(
            platform=None,
            with_penpot=False,
            context_mode=None,
            languages=(),
            check_only=False,
            force_scaffold=False,
            deploy_after=False,
            dry_run=False,
            show_diff=False,
        )
    assert _mode(tmp_path) == "markdown"
