"""Persistent hash cache for deployed instruction files.

PlatformAdapter records the SHA256 of each instruction file at deploy
time and consults the cache before overwriting on next deploy. The cache
lives at ``.cataforge/.instruction-hashes.json`` (project-local, gitignored).
"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json

_INSTRUCTION_HASHES_REL = ".cataforge/.instruction-hashes.json"


def load_instruction_hashes(project_root: Path) -> dict[str, str]:
    path = project_root / _INSTRUCTION_HASHES_REL
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except ConfigError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def save_instruction_hashes(
    project_root: Path, hashes: dict[str, str]
) -> None:
    path = project_root / _INSTRUCTION_HASHES_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
