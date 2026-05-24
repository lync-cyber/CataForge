"""Tests for EventBus.emit OSError resilience."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cataforge.core.events import EventBus


class TestEventEmitOSError:
    def test_emit_oserror_does_not_raise(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        log_file = tmp_path / "events.jsonl"
        bus = EventBus(log_path=log_file)

        with (
            patch("builtins.open", side_effect=OSError("disk full")),
            caplog.at_level(logging.WARNING, logger="cataforge"),
        ):
            bus.emit("test:event", {"key": "value"})

        assert any(
            "disk full" in record.message and record.levelno == logging.WARNING
            for record in caplog.records
        )

    def test_emit_oserror_handlers_still_called(self, tmp_path: Path) -> None:
        log_file = tmp_path / "events.jsonl"
        bus = EventBus(log_path=log_file)
        received = []
        bus.on("test:event", received.append)

        with patch("builtins.open", side_effect=OSError("disk full")):
            ev = bus.emit("test:event", {"x": 1})

        assert len(received) == 1
        assert received[0].name == "test:event"
        assert ev is not None

    def test_emit_oserror_warning_contains_path(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        log_file = tmp_path / "events.jsonl"
        bus = EventBus(log_path=log_file)

        with (
            patch("builtins.open", side_effect=OSError("disk full")),
            caplog.at_level(logging.WARNING, logger="cataforge"),
        ):
            bus.emit("test:event")

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("disk full" in m for m in warning_messages)

    def test_emit_no_log_path_never_opens(self) -> None:
        bus = EventBus()
        mock_open = MagicMock()
        with patch("builtins.open", mock_open):
            bus.emit("test:event")
        mock_open.assert_not_called()
