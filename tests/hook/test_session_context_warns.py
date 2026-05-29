"""session_start logging is best-effort: warns on failure, never raises,
and never runs a deploy."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cataforge.runtime.hook.scripts import session_context
from cataforge.runtime.hook.scripts.session_context import _log_session_start


def test_log_session_start_warns_on_failure(capsys):
    exc = OSError("event log unwritable")
    with patch("cataforge.core.event_log.append_event", side_effect=exc):
        _log_session_start()

    captured = capsys.readouterr()
    assert "warn" in captured.err
    assert "session_start" in captured.err


def test_log_session_start_does_not_raise():
    exc = OSError("event log unwritable")
    with patch("cataforge.core.event_log.append_event", side_effect=exc):
        try:
            _log_session_start()
        except Exception as e:
            pytest.fail(f"_log_session_start raised unexpectedly: {e}")


def test_session_start_appends_event(tmp_path, monkeypatch):
    (tmp_path / ".cataforge").mkdir()
    monkeypatch.chdir(tmp_path)
    _log_session_start()

    log = tmp_path / "docs" / "EVENT-LOG.jsonl"
    assert log.is_file()
    assert '"event": "session_start"' in log.read_text(encoding="utf-8")


def test_hook_does_not_deploy() -> None:
    """Regression: the SessionStart hook must not shell out to `cataforge
    deploy` — opening a session must not mutate tracked files."""
    import inspect

    src = inspect.getsource(session_context)
    assert "deploy" not in src
    assert not hasattr(session_context, "_auto_deploy")
