"""Dispatch helpers for Group A call sites.

Every legacy Group A entry point in :mod:`cataforge.docs.loader`,
:mod:`cataforge.docs.indexer`, and the doc-review checker decides at
call time whether to read from the KG or fall back to the legacy
file-based code path. The decision hinges on
`KGConfig.kg_active_doc_types` resolved per project.

Resolution layer:

* `.cataforge/framework.json` ``kg.kg_active_doc_types`` list (if
  declared and non-empty) wins. Project authors flip this when they
  want to opt out / promote per Task 7 §7.5.
* Otherwise the dataclass default applies. Until Commit 5 of
  sub-PR 5 lands, the dataclass default is an empty set (= legacy for
  everything); Commit 5 flips it to `{prd, arch, test}`.

The helpers also cache per-project decisions to avoid re-reading
`framework.json` on every Group A call.
"""
from __future__ import annotations

import json
from pathlib import Path

from cataforge.kg._config import KGConfig

_ACTIVE_CACHE: dict[str, set[str]] = {}
_CONFIG_CACHE: dict[str, KGConfig] = {}


def _project_root_key(project_root: str | Path) -> str:
    return str(Path(project_root).resolve())


def _read_framework_json(project_root: Path) -> dict:
    path = project_root / ".cataforge" / "framework.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def active_doc_types(project_root: str | Path) -> set[str]:
    """Resolve the active doc_type set for `project_root` (cached)."""
    key = _project_root_key(project_root)
    cached = _ACTIVE_CACHE.get(key)
    if cached is not None:
        return cached

    data = _read_framework_json(Path(project_root))
    kg_section = data.get("kg") or {}
    declared = kg_section.get("kg_active_doc_types")
    if isinstance(declared, list) and all(isinstance(d, str) for d in declared):
        resolved = set(declared)
    else:
        resolved = set(KGConfig().kg_active_doc_types)

    _ACTIVE_CACHE[key] = resolved
    return resolved


def kg_config_for(project_root: str | Path) -> KGConfig:
    """Return a `KGConfig` populated from `framework.json` + defaults."""
    key = _project_root_key(project_root)
    cached = _CONFIG_CACHE.get(key)
    if cached is not None:
        return cached

    project_root = Path(project_root)
    db_path = project_root / ".cataforge" / "kg" / "store"
    active = active_doc_types(project_root)

    cfg = KGConfig(db_path=db_path, kg_active_doc_types=active)
    _CONFIG_CACHE[key] = cfg
    return cfg


def is_active_for(doc_type: str, project_root: str | Path) -> bool:
    """True iff `doc_type` is in the active set AND a KG store exists.

    A non-existent store is treated as "not active" — callers fall back
    to the legacy path even if the framework.json lists the doc_type,
    because there's nothing to query yet. The doctor's
    `kg_ingestion_completeness` gate surfaces the missing store as a
    skipped check; callers don't have to deal with it.
    """
    if doc_type not in active_doc_types(project_root):
        return False
    db_path = Path(project_root) / ".cataforge" / "kg" / "store"
    return db_path.exists()


def invalidate_cache() -> None:
    """Clear all dispatch caches. Test-only helper."""
    _ACTIVE_CACHE.clear()
    _CONFIG_CACHE.clear()


__all__ = [
    "active_doc_types",
    "invalidate_cache",
    "is_active_for",
    "kg_config_for",
]
