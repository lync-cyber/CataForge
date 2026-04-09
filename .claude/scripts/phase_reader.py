#!/usr/bin/env python3
"""Shared utility: read current project phase from CLAUDE.md.

Used by hooks (session_context, validate_agent_result, log_agent_dispatch)
to avoid duplicating the CLAUDE.md parsing logic.
"""

import os


def _find_project_root():
    """Locate project root by traversing up from this script's location."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(2):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d


def read_current_phase(project_dir=None):
    """Read the '当前阶段' field from CLAUDE.md.

    Args:
        project_dir: Project root directory. Auto-detected if None.

    Returns:
        Phase string (e.g. 'architecture'), or 'unknown' if not found.
    """
    if project_dir is None:
        project_dir = _find_project_root()

    claude_md = os.path.join(project_dir, "CLAUDE.md")
    if not os.path.isfile(claude_md):
        return "unknown"

    try:
        with open(claude_md, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("- 当前阶段:"):
                    raw = line.split(":", 1)[1].strip()
                    # Skip unresolved template placeholders like {requirements|...}
                    if raw.startswith("{"):
                        return "unknown"
                    return raw.split("|")[0].strip()
    except OSError:
        pass

    return "unknown"
