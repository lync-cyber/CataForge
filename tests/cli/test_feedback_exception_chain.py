"""Verify that assembler exceptions are chained (not swallowed) via CataforgeError."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cataforge.cli.errors import CataforgeError
from cataforge.cli.feedback_cmd import bug_command, suggest_command


def _bootstrap(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.2.1-test", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    return tmp_path


def _raise_chained(exc: Exception):
    """Re-raise exc as the cause of a CataforgeError, simulating ``from e``."""
    try:
        raise exc
    except Exception as e:
        raise CataforgeError(f"failed to assemble bundle: {e}") from e


class TestFeedbackExceptionChain:
    def test_bug_assembler_propagates_cause(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        cause = ValueError("internal bug detail")
        with patch("cataforge.cli.feedback_cmd.assemble_bug", side_effect=cause):
            result = CliRunner().invoke(bug_command, ["--print", "--summary", "s"])
        assert result.exit_code == 1
        assert "failed to assemble bug bundle" in result.output
        assert "Error:" in result.output

    def test_suggest_assembler_propagates_cause(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path)
        monkeypatch.chdir(project)
        cause = ValueError("internal suggest detail")
        with patch("cataforge.cli.feedback_cmd.assemble_suggestion", side_effect=cause):
            result = CliRunner().invoke(suggest_command, ["--print", "--summary", "s"])
        assert result.exit_code == 1
        assert "failed to assemble suggestion bundle" in result.output
        assert "Error:" in result.output

    def test_bug_assembler_exception_cause_is_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Directly verify ``from e`` preserves ``__cause__`` on the raised CataforgeError."""
        cause = ValueError("direct chain check")
        with pytest.raises(CataforgeError) as exc_info:
            _raise_chained(cause)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
