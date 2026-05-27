"""Verify _auto_deploy emits a stderr warning on failure and does not raise."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cataforge.hook.scripts.session_context import _auto_deploy


def test_auto_deploy_warns_on_failure(capsys):
    exc = FileNotFoundError("cataforge not in PATH")
    with patch("cataforge.hook.scripts.session_context.run_proc", side_effect=exc):
        _auto_deploy()

    captured = capsys.readouterr()
    assert "warn" in captured.err
    assert "auto-deploy" in captured.err
    assert "cataforge not in PATH" in captured.err


def test_auto_deploy_does_not_raise(capsys):
    exc = FileNotFoundError("cataforge not in PATH")
    with patch("cataforge.hook.scripts.session_context.run_proc", side_effect=exc):
        try:
            _auto_deploy()
        except Exception as e:
            pytest.fail(f"_auto_deploy raised unexpectedly: {e}")
