"""SessionStart Hook: record a session_start event.

Best-effort only: opening an IDE session must never mutate tracked files
or shell out to other commands. The event is appended to the gitignored
``docs/EVENT-LOG.jsonl``; any failure degrades to a stderr warning.
"""

import sys
from pathlib import Path

from cataforge.runtime.hook.base import hook_main, read_hook_input

# IDE multi-window / reconnect fires SessionStart in bursts; suppress
# duplicates landing within this window.
_DEBOUNCE_SECONDS = 60
_TAIL_BYTES = 8192


def _recent_session_start(project_root: Path) -> bool:
    """True when a session_start within the debounce window already exists."""
    import json
    from datetime import UTC, datetime

    from cataforge.core.event_log import event_log_path

    path = event_log_path(project_root)
    if not path.is_file():
        return False
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - _TAIL_BYTES))
        tail = f.read().decode("utf-8", errors="replace")
    now = datetime.now(UTC)
    for line in reversed(tail.splitlines()):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict) or rec.get("event") != "session_start":
            continue
        try:
            ts = datetime.fromisoformat(str(rec.get("ts")).replace("Z", "+00:00"))
        except ValueError:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return (now - ts).total_seconds() < _DEBOUNCE_SECONDS
    return False


def _log_session_start() -> None:
    """Append a session_start event (debounced); warn (never raise) on failure."""
    try:
        from cataforge.core.event_log import append_event, now_iso
        from cataforge.core.paths import find_project_root

        root = find_project_root()
        if _recent_session_start(root):
            return
        append_event(
            root,
            {
                "ts": now_iso(),
                "event": "session_start",
                "phase": "session",
                "detail": "IDE session started",
            },
        )
    except Exception as e:
        print(f"warn: session_start log skipped: {e}", file=sys.stderr)


@hook_main
def main() -> None:
    read_hook_input()
    _log_session_start()
    sys.exit(0)


if __name__ == "__main__":
    main()
