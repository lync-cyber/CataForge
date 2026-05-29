"""SessionStart Hook: record a session_start event.

Best-effort only: opening an IDE session must never mutate tracked files
or shell out to other commands. The event is appended to the gitignored
``docs/EVENT-LOG.jsonl``; any failure degrades to a stderr warning.
"""

import sys

from cataforge.hook.base import hook_main, read_hook_input


def _log_session_start() -> None:
    """Append a session_start event; warn (never raise) on failure."""
    try:
        from cataforge.core.event_log import append_event, now_iso
        from cataforge.core.paths import find_project_root

        append_event(
            find_project_root(),
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
