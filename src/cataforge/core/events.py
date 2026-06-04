"""Framework event bus — structured logging, tracing, and debug support."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("cataforge")

EventHandler = Callable[["Event"], None]


class Event:
    """Immutable event record."""

    __slots__ = ("timestamp", "name", "data")

    def __init__(self, name: str, data: dict[str, Any] | None = None) -> None:
        self.timestamp = datetime.now(UTC).isoformat()
        self.name = name
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp": self.timestamp, "event": self.name, "data": self.data}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventBus:
    """Pub-sub event bus with optional file-based event log."""

    def __init__(self, log_path: Path | None = None) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._log_path = log_path

    def emit(self, event_name: str, data: dict[str, Any] | None = None) -> Event:
        """Fire an event: log it, persist it, then call handlers."""
        ev = Event(event_name, data)
        logger.debug("EVENT %s | %s", event_name, json.dumps(ev.data, ensure_ascii=False))

        if self._log_path:
            try:
                with open(self._log_path, "a") as f:
                    f.write(ev.to_json() + "\n")
            except OSError as e:
                logger.warning("Event log write failed (%s): %s", self._log_path, e)

        for handler in self._global_handlers:
            _safe_call(handler, ev)

        for handler in self._handlers.get(event_name, []):
            _safe_call(handler, ev)

        return ev

    def on(self, event_name: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_name, []).append(handler)

    def on_all(self, handler: EventHandler) -> None:
        """Register a handler that receives every event."""
        self._global_handlers.append(handler)

    def off(self, event_name: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    def clear(self) -> None:
        self._handlers.clear()
        self._global_handlers.clear()


def _safe_call(handler: EventHandler, ev: Event) -> None:
    try:
        handler(ev)
    except Exception as e:
        logger.exception("Event handler %s failed for %s", handler, ev.name)
        # When the logger is silent (typical CLI session has the
        # cataforge logger at WARNING and no stderr handler attached
        # at all), the exception above writes to nothing visible.
        # Drop a one-liner to stderr so a broken event handler can't
        # vanish without any user-facing trace. ``core`` deliberately
        # uses ``sys.stderr.write`` rather than click.echo to keep
        # this module free of CLI deps.
        if logger.getEffectiveLevel() > logging.ERROR:
            sys.stderr.write(
                f"[events] handler {handler!r} failed for {ev.name!r}: {type(e).__name__}: {e}\n"
            )


# Well-known event names
FRAMEWORK_SETUP = "framework:setup"
FRAMEWORK_DEPLOY = "framework:deploy"
FRAMEWORK_UPGRADE = "framework:upgrade"
AGENT_DISPATCH = "agent:dispatch"
AGENT_COMPLETE = "agent:complete"
SKILL_START = "skill:start"
SKILL_COMPLETE = "skill:complete"
HOOK_EXECUTE = "hook:execute"
HOOK_DEGRADED = "hook:degraded"
MCP_REGISTER = "mcp:register"
MCP_START = "mcp:start"
MCP_STOP = "mcp:stop"
MCP_HEALTH = "mcp:health_check"
PLUGIN_LOAD = "plugin:load"
PLUGIN_ERROR = "plugin:error"
