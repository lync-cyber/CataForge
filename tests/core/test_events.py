"""Tests for event bus."""

from __future__ import annotations

from pathlib import Path

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
