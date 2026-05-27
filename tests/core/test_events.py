"""Tests for event bus."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from cataforge.core.events import Event, EventBus


class TestEventBus:
    def test_emit_and_handle(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.on("test:event", received.append)

        bus.emit("test:event", {"key": "value"})
        assert len(received) == 1
        assert received[0].name == "test:event"
        assert received[0].data["key"] == "value"

    def test_global_handler(self) -> None:
        bus = EventBus()
        all_events: list[Event] = []
        bus.on_all(all_events.append)

        bus.emit("event:a")
        bus.emit("event:b")
        assert len(all_events) == 2

    def test_file_logging(self, tmp_path: Path) -> None:
        log_file = tmp_path / "events.jsonl"
        bus = EventBus(log_path=log_file)

        bus.emit("test:log", {"data": 42})
        bus.emit("test:log2")

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_off(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.on("test:event", received.append)
        bus.emit("test:event")
        assert len(received) == 1

        bus.off("test:event", received.append)
        bus.emit("test:event")
        assert len(received) == 1

    def test_handler_exception_does_not_propagate(self) -> None:
        bus = EventBus()

        def bad_handler(ev: Event) -> None:
            raise ValueError("boom")

        bus.on("test:event", bad_handler)
        bus.emit("test:event")  # should not raise

    def test_handler_failure_writes_to_stderr_when_logger_silent(
        self, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
    ) -> None:
        """C6: typical CLI runs leave the ``cataforge`` logger at
        WARNING+ with no stderr handler attached, so a broken event
        handler's ``logger.exception`` call produces no visible output
        anywhere. _safe_call must drop a one-liner to ``sys.stderr``
        in that case so handler bugs cannot vanish silently.
        """
        logger = logging.getLogger("cataforge")
        prior_level = logger.level
        try:
            # Force logger above ERROR so the fallback branch fires.
            logger.setLevel(logging.CRITICAL)

            bus = EventBus()

            def bad_handler(ev: Event) -> None:
                raise ValueError("simulated handler bug")

            bus.on("test:silent", bad_handler)
            bus.emit("test:silent")  # must not raise
        finally:
            logger.setLevel(prior_level)

        captured = capsys.readouterr()
        assert "[events] handler" in captured.err
        assert "simulated handler bug" in captured.err
        assert "ValueError" in captured.err

    def test_handler_failure_does_not_duplicate_to_stderr_when_logger_active(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Symmetric to the above: when the logger IS active at ERROR
        level (e.g. user passed ``--verbose``), the fallback must NOT
        also write to stderr — otherwise a single failure shows up
        twice."""
        logger = logging.getLogger("cataforge")
        prior_level = logger.level
        try:
            logger.setLevel(logging.ERROR)

            bus = EventBus()

            def bad_handler(ev: Event) -> None:
                raise ValueError("active-logger handler bug")

            bus.on("test:active", bad_handler)
            bus.emit("test:active")
        finally:
            logger.setLevel(prior_level)

        captured = capsys.readouterr()
        assert "[events]" not in captured.err, (
            "fallback must not duplicate output when logger handles ERROR"
        )
