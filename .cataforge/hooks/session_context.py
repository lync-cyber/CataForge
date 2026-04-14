#!/usr/bin/env python3
"""SessionStart Hook: Log session_start event to EVENT-LOG.jsonl.

Design notes:
  - Hook-injected context has low attention weight for the LLM, so env info
    is baked into CLAUDE.md via setup.py --emit-env-block at Bootstrap time.
  - This hook's sole responsibility is auditing: append a session_start
    event so reflector can reconstruct session history. Dedup guards
    against duplicate entries on auto-compact.

Test:
  echo '{}' | python .cataforge/hooks/session_context.py
  Expected: exit 0, one session_start line appended (unless dedup hit).
"""

import json
import os
import sys
from datetime import datetime, timezone

from _hook_base import hook_main, read_hook_input

# Shared utilities (.cataforge/scripts/framework + lib)
_scripts = os.path.join(os.path.dirname(__file__), "..", "scripts")
for _p in (
    os.path.join(_scripts, "lib"),
    os.path.join(_scripts, "framework"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from event_logger import append_event as _log_event
except ImportError:
    _log_event = None

try:
    from phase_reader import read_current_phase as _read_phase
except ImportError:
    _read_phase = None


def _should_log_session_start(project_dir: str) -> bool:
    """Skip logging if a session_start event was written within the last 60s.

    Prevents duplicate entries when Claude Code fires both SessionStart and
    an immediate auto-compact event.
    """
    log_path = os.path.join(project_dir, "docs", "EVENT-LOG.jsonl")
    if not os.path.isfile(log_path):
        return True
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines[-5:]):
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if entry.get("event") == "session_start":
                ts = datetime.fromisoformat(entry["ts"])
                if (datetime.now(timezone.utc) - ts).total_seconds() < 60:
                    return False
                break
    except Exception:
        pass
    return True


def _auto_deploy():
    """会话启动时自动运行 deploy 同步（PROJECT-STATE.md → CLAUDE.md）。"""
    try:
        import subprocess
        cataforge_dir = os.path.join(os.path.dirname(__file__), "..")
        deploy_script = os.path.join(cataforge_dir, "scripts", "framework", "deploy.py")
        if os.path.isfile(deploy_script):
            subprocess.run(
                [sys.executable, deploy_script],
                timeout=15, capture_output=True,
            )
    except Exception:
        pass


@hook_main
def main():
    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    cataforge_dir = os.path.dirname(hooks_dir)
    project_dir = os.path.dirname(cataforge_dir)

    _auto_deploy()

    if _log_event and _should_log_session_start(project_dir):
        phase = _read_phase(project_dir) if _read_phase else "unknown"
        try:
            _log_event(
                event="session_start",
                phase=phase,
                detail="会话启动",
            )
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
