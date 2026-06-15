"""`cataforge setup --context-strategy` selects the document-driving backend.

Couples with the doc-only KG-bypass: selecting doc-only must both persist
``context.strategy`` and make ``kg_enabled`` report False.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli import setup_cmd
from cataforge.interface.cli.setup_cmd import setup_command


def _strategy(root: Path) -> str:
    data = json.loads((root / ".cataforge" / "framework.json").read_text(encoding="utf-8"))
    return (data.get("context") or {}).get("strategy")


def test_flag_doc_only_persists_and_disables_kg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache, kg_enabled

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, ["--context-strategy", "doc-only"])
    assert result.exit_code == 0, result.output
    assert _strategy(tmp_path) == "doc-only"

    invalidate_cache()
    assert kg_enabled(tmp_path) is False
    invalidate_cache()


def test_flag_kg_first_persists_and_enables_kg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache, kg_enabled

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, ["--context-strategy", "kg-first"])
    assert result.exit_code == 0, result.output
    assert _strategy(tmp_path) == "kg-first"

    invalidate_cache()
    assert kg_enabled(tmp_path) is True
    invalidate_cache()


def test_non_interactive_defaults_to_kg_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No flag + no TTY → scaffold default (kg-first) is untouched, no prompt."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(setup_command, [])
    assert result.exit_code == 0, result.output
    assert _strategy(tmp_path) == "kg-first"


def test_interactive_prompt_selects_doc_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh interactive install with no flag prompts; choosing markdown → doc-only."""
    import click

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(setup_cmd, "_prompt_context_strategy", lambda: "doc-only")

    # The setup group callback reads the active context's invoked_subcommand;
    # drive it under a real context (no subcommand → init path runs).
    ctx = click.Context(setup_command)
    with ctx:
        setup_command.callback(
            platform=None,
            with_penpot=False,
            context_strategy=None,
            languages=(),
            check_only=False,
            force_scaffold=False,
            deploy_after=False,
            dry_run=False,
            show_diff=False,
        )
    assert _strategy(tmp_path) == "doc-only"
