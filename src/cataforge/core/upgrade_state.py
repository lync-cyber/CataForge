"""Run-state persisted at ``.cataforge/state/upgrade.json`` (gitignored).

Framework bookkeeping that must never live in the shared config file —
currently the ``event_log_validate_since`` watermark. Reads fall back to
the pre-migration location (``framework.json#upgrade.state``) so doctor
works on projects that have not run ``cataforge config migrate`` yet.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.utils.atomic_write import atomic_write_text

if TYPE_CHECKING:
    from cataforge.core.paths import ProjectPaths


def read_upgrade_state(paths: ProjectPaths) -> dict[str, Any]:
    """Current run-state dict; legacy framework.json location as fallback."""
    state_path = paths.upgrade_state
    if state_path.is_file():
        try:
            data = read_json(state_path)
            if isinstance(data, dict):
                return data
        except ConfigError:
            pass
    try:
        raw = read_json(paths.framework_json)
    except ConfigError:
        return {}
    if not isinstance(raw, dict):
        return {}
    legacy = (raw.get("upgrade") or {}).get("state")
    return dict(legacy) if isinstance(legacy, dict) else {}


def write_upgrade_state(paths: ProjectPaths, state: dict[str, Any]) -> None:
    atomic_write_text(
        paths.upgrade_state,
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
    )
