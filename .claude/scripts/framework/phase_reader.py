#!/usr/bin/env python3
"""Shared utility: read current project phase from CLAUDE.md.

Used by hooks (session_context, validate_agent_result, log_agent_dispatch)
to avoid duplicating the CLAUDE.md parsing logic.
"""

import os
import re
import sys

_FRAMEWORK_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_ROOT = os.path.dirname(_FRAMEWORK_DIR)
_LIB = os.path.join(_SCRIPTS_ROOT, "lib")
for _p in (_LIB, _FRAMEWORK_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from _common import find_project_root

_PHASE_RE = re.compile(r"^\s*-\s*当前阶段:\s*(.+)$")


def read_current_phase(project_dir=None):
    """Read the '当前阶段' field from CLAUDE.md.

    Args:
        project_dir: Project root directory. Auto-detected if None.

    Returns:
        Phase string (e.g. 'architecture'), or 'unknown' if not found.
    """
    if project_dir is None:
        project_dir = find_project_root()

    claude_md = os.path.join(project_dir, "CLAUDE.md")
    if not os.path.isfile(claude_md):
        return "unknown"

    try:
        with open(claude_md, "r", encoding="utf-8") as f:
            for line in f:
                m = _PHASE_RE.match(line)
                if m:
                    raw = m.group(1).strip()
                    # Skip unresolved template placeholders like {requirements|...}
                    if raw.startswith("{"):
                        return "unknown"
                    return raw.split("|")[0].strip()
    except OSError:
        pass

    return "unknown"
