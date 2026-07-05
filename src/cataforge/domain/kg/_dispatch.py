"""Dispatch helpers for legacy entry points in the docs layer.

Every entry point in :mod:`cataforge.domain.docs.loader`,
:mod:`cataforge.domain.docs.indexer`, and the doc-review checker decides at
call time whether to read from the KG or fall back to the legacy
file-based code path. The decision hinges on
`KGConfig.kg_active_doc_types` resolved per project.

Resolution layer:

* `.cataforge/framework.json` ``kg.kg_active_doc_types`` list (if
  declared and non-empty) wins.
* Otherwise the dataclass default applies.

The helpers also cache per-project decisions to avoid re-reading
`framework.json` on every call.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from cataforge.core.config import ConfigManager
from cataforge.domain.kg._config import DEFAULT_DEFINITION_AUTHORITY, KGConfig

_ACTIVE_CACHE: dict[str, set[str]] = {}
_AUTHORITY_CACHE: dict[str, dict[str, frozenset[str]]] = {}
_CUSTOM_PREFIX_CACHE: dict[str, dict[str, str]] = {}
_CONFIG_CACHE: dict[str, KGConfig] = {}
_MODE_CACHE: dict[str, str] = {}
_DISPATCH_LOCK = threading.Lock()

# The single source-of-truth axis a project selects via `framework.json`
# ``context.mode``:
#   ``markdown`` — Markdown is canonical; no graph backend at all.
#   ``graph``    — the graph is canonical; Markdown is an exported view that
#                  agents author through ``context write*``.
MODES: frozenset[str] = frozenset({"markdown", "graph"})
DEFAULT_MODE = "graph"


def _project_root_key(project_root: str | Path) -> str:
    return str(Path(project_root).resolve())


def _read_framework_json(project_root: Path) -> dict[str, Any]:
    try:
        return ConfigManager(project_root).load_raw()
    except (OSError, ValueError):
        return {}


def active_doc_types(project_root: str | Path) -> set[str]:
    """Resolve the active doc_type set for `project_root` (cached).

    The set lives at ``context.kg_active_doc_types``. A well-formed list
    wins even when empty (an explicit empty list means legacy-only); an
    absent or malformed value applies the dataclass default.
    """
    key = _project_root_key(project_root)
    with _DISPATCH_LOCK:
        cached = _ACTIVE_CACHE.get(key)
        if cached is not None:
            return cached

        data = _read_framework_json(Path(project_root))
        declared = (data.get("context") or {}).get("kg_active_doc_types")
        if isinstance(declared, list) and all(isinstance(d, str) for d in declared):
            resolved = set(declared)
        else:
            resolved = set(KGConfig().kg_active_doc_types)

        _ACTIVE_CACHE[key] = resolved
        return resolved


def definition_authority(project_root: str | Path) -> dict[str, frozenset[str]]:
    """Resolve class-name → authoritative doc_types for `project_root` (cached).

    Defaults come from :data:`DEFAULT_DEFINITION_AUTHORITY`. A well-formed
    ``context.kg_definition_authority`` mapping (``{class_name: [doc_type,
    ...]}``) extends the per-class default — merge is additive, an extension
    never narrows. Malformed entries are ignored.
    """
    key = _project_root_key(project_root)
    with _DISPATCH_LOCK:
        cached = _AUTHORITY_CACHE.get(key)
        if cached is not None:
            return cached

        data = _read_framework_json(Path(project_root))
        declared = (data.get("context") or {}).get("kg_definition_authority")
        resolved = dict(DEFAULT_DEFINITION_AUTHORITY)
        if isinstance(declared, dict):
            for class_name, doc_types in declared.items():
                if (
                    isinstance(class_name, str)
                    and isinstance(doc_types, list)
                    and all(isinstance(d, str) for d in doc_types)
                ):
                    resolved[class_name] = resolved.get(class_name, frozenset()) | frozenset(
                        doc_types
                    )

        _AUTHORITY_CACHE[key] = resolved
        return resolved


def custom_entity_prefixes(project_root: str | Path) -> dict[str, str]:
    """Resolve ``{entity_id_prefix: domain_type}`` for `project_root` (cached).

    Reads ``kg.custom_entity_prefixes`` from ``framework.json``. Only
    well-formed ``str → str`` entries are kept; a prefix that collides with a
    core prefix is retained here but never shadows core at extraction time.
    An absent or malformed value yields an empty registry (closed ontology).
    """
    key = _project_root_key(project_root)
    with _DISPATCH_LOCK:
        cached = _CUSTOM_PREFIX_CACHE.get(key)
        if cached is not None:
            return cached

        data = _read_framework_json(Path(project_root))
        declared = (data.get("kg") or {}).get("custom_entity_prefixes")
        resolved: dict[str, str] = {}
        if isinstance(declared, dict):
            resolved = {
                p: dt for p, dt in declared.items() if isinstance(p, str) and isinstance(dt, str)
            }

        _CUSTOM_PREFIX_CACHE[key] = resolved
        return resolved


def context_mode(project_root: str | Path) -> str:
    """Resolve the context source-of-truth mode for `project_root` (cached).

    Returns one of :data:`MODES`; an absent or unrecognized value resolves to
    :data:`DEFAULT_MODE` (``graph``). Legacy ``context.strategy`` /
    ``context.authoring`` are not read — the doctor flags them and
    ``cataforge upgrade apply`` rewrites them to ``context.mode``.
    """
    key = _project_root_key(project_root)
    with _DISPATCH_LOCK:
        cached = _MODE_CACHE.get(key)
        if cached is not None:
            return cached

        data = _read_framework_json(Path(project_root))
        declared = (data.get("context") or {}).get("mode")
        resolved = declared if declared in MODES else DEFAULT_MODE

        _MODE_CACHE[key] = resolved
        return resolved


def kg_enabled(project_root: str | Path) -> bool:
    """True iff the project has a graph backend (``graph`` mode).

    Under ``markdown`` the graph is not a backend at all: every KG gate
    (read resolution, doc-review coverage, ingest scope) bypasses to the
    Markdown/file path regardless of which doc_types are listed active.
    """
    return context_mode(project_root) != "markdown"


def kg_config_for(project_root: str | Path) -> KGConfig:
    """Return a `KGConfig` populated from `framework.json` + defaults."""
    key = _project_root_key(project_root)
    with _DISPATCH_LOCK:
        cached = _CONFIG_CACHE.get(key)
        if cached is not None:
            return cached

    project_root = Path(project_root)
    data = _read_framework_json(project_root)
    kg_section = data.get("kg") or {}

    default_db = project_root / ".cataforge" / "kg" / "store"
    raw_db = kg_section.get("db_path")
    db_path = (project_root / raw_db) if raw_db else default_db

    active = active_doc_types(project_root)

    defaults = KGConfig()
    cfg = KGConfig(
        store_backend=kg_section.get("store_backend", defaults.store_backend),
        db_path=db_path,
        governance=kg_section.get("governance", defaults.governance),
        coverage_mode=kg_section.get("coverage_mode", defaults.coverage_mode),
        base_namespace=kg_section.get("base_namespace", defaults.base_namespace),
        ontology_namespace=kg_section.get("ontology_namespace", defaults.ontology_namespace),
        kg_active_doc_types=active,
    )
    with _DISPATCH_LOCK:
        _CONFIG_CACHE[key] = cfg
    return cfg


def is_active_for(doc_type: str, project_root: str | Path) -> bool:
    """True iff KG is enabled, `doc_type` is active, AND a KG store exists.

    Under `markdown` mode this is always False — the graph is not a
    backend, so a stray store on disk never reactivates KG gates. A
    non-existent store is likewise treated as "not active": callers fall
    back to the legacy path even if framework.json lists the doc_type,
    because there's nothing to query yet. The doctor's
    `kg_ingestion_completeness` gate surfaces the missing store as a
    skipped check; callers don't have to deal with it.
    """
    if not kg_enabled(project_root):
        return False
    if doc_type not in active_doc_types(project_root):
        return False
    db_path = Path(project_root) / ".cataforge" / "kg" / "store"
    return db_path.exists()


def invalidate_cache() -> None:
    """Clear all dispatch caches."""
    with _DISPATCH_LOCK:
        _ACTIVE_CACHE.clear()
        _AUTHORITY_CACHE.clear()
        _CUSTOM_PREFIX_CACHE.clear()
        _CONFIG_CACHE.clear()
        _MODE_CACHE.clear()


__all__ = [
    "DEFAULT_MODE",
    "MODES",
    "active_doc_types",
    "context_mode",
    "custom_entity_prefixes",
    "definition_authority",
    "invalidate_cache",
    "is_active_for",
    "kg_config_for",
    "kg_enabled",
]
