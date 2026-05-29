"""Backward-compatible shims for 0.4.x business-doc call points.

Every public entry point dispatches on `doc_type in KGConfig.kg_active_doc_types`
(per-doc_type rolling cutover). The KG branch runs against a `KnowledgeGraph`
connection; the legacy branch delegates to :mod:`cataforge.docs.loader`
and :mod:`cataforge.docs.indexer` so non-active doc_types continue to
work exactly as in 0.4.x.

All shims emit `DeprecationWarning` once per call — they are removed
in 0.6.0; callers should migrate to the typed `KnowledgeGraph` API.

Connection lifecycle
--------------------
Each shim accepts an optional ``kg: KnowledgeGraph`` parameter. When
provided, the shim uses that already-open connection — tests and
batched callers pass a single facade rather than reopening the store
per call. When omitted, the shim builds a `KGConfig` for
`project_root` and opens a transient connection. Both paths converge
on the same code; the lifecycle handling is a thin wrapper.

Framework-asset call points (skill loading, agent registry, rule
evaluation) deliberately have no shim — they access `.cataforge/`
filesystem assets directly and are unaffected by the KG migration.
"""

from __future__ import annotations

import logging
import warnings
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any

from cataforge.kg._config import KGConfig
from cataforge.kg._sparql_utils import (
    _row_lookup,
    _strv,
    cf_namespace,
    escape_sparql_literal,
)
from cataforge.kg.facade import KnowledgeGraph
from cataforge.utils.md_parse import slice_section

logger = logging.getLogger(__name__)

# Legacy path estimate; KG path uses actual rendered token count.
_LEGACY_TOKEN_PER_REF = 200

# ---------------------------------------------------------------------------
# Config / dispatch helpers
# ---------------------------------------------------------------------------


def _config_for(
    project_root: str | Path,
    *,
    db_path: str | Path | None = None,
    overrides: KGConfig | None = None,
) -> KGConfig:
    """Build a `KGConfig` for `project_root`.

    `overrides` (when given) wins: tests inject an explicit `KGConfig`
    with a specific `store_backend` / `kg_active_doc_types`. Otherwise
    the default dataclass values apply, with `db_path` resolved under
    `<project_root>/.cataforge/kg/store/` unless overridden.
    """
    if overrides is not None:
        return overrides
    if db_path is None:
        db_path = Path(project_root) / ".cataforge" / "kg" / "store"
    return KGConfig(db_path=Path(db_path))


def _doc_type_is_active(doc_type: str, config: KGConfig) -> bool:
    return doc_type in config.kg_active_doc_types


def _emit(name: str, replacement: str) -> None:
    warnings.warn(
        f"cataforge.kg._shim.{name}() is deprecated since 0.5.0; "
        f"use {replacement} instead. Removal scheduled for 0.6.0.",
        DeprecationWarning,
        stacklevel=3,
    )


def _kg_session(
    config: KGConfig,
    *,
    kg: KnowledgeGraph | None,
) -> AbstractContextManager[KnowledgeGraph]:
    """Return a context manager yielding a KnowledgeGraph.

    When `kg` is provided, wraps it in a `nullcontext` so the caller's
    `with _kg_session(...) as k:` block does not close the borrowed
    connection. Otherwise opens a transient connection via `connect()`.
    """
    if kg is not None:
        return nullcontext(kg)
    return KnowledgeGraph.connect(config)


# ---------------------------------------------------------------------------
# Shim 1 — extract
# ---------------------------------------------------------------------------


def extract(
    doc_type: str,
    section_id: str,
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    config: KGConfig | None = None,
    kg: KnowledgeGraph | None = None,
) -> dict[str, Any] | None:
    """Extract a single entity by `doc_type` + `section_id`.

    KG branch: SPARQL lookup keyed on the entity_id parsed from
    `section_id`, falling back to a literal `cf:source_section` match.
    Returns a flat dict with `uri`, `entity_id`, `title`, `status`,
    `_class`, `source_doc`, `source_section`, `doc_type`.

    Legacy branch: delegates to :func:`cataforge.docs.loader.extract`
    on the reconstructed `<doc_type>#<section_id>` ref. Wraps the text
    result in a dict with the original text in `body`.
    """
    _emit("extract", "kg.query.entity() or kg.query.<type>()")
    cfg = _config_for(project_root, db_path=db_path, overrides=config)
    if _doc_type_is_active(doc_type, cfg):
        return _kg_extract(doc_type, section_id, cfg, kg=kg)
    return _legacy_extract(doc_type, section_id, project_root)


def _kg_extract(
    doc_type: str,
    section_id: str,
    config: KGConfig,
    *,
    kg: KnowledgeGraph | None = None,
) -> dict[str, Any] | None:
    """Resolve `(doc_type, section_id)` to a flat entity record.

    Resolution order:

    1. Parse an entity_id (``F-001`` / ``AC-014`` …) out of `section_id`
       — the common anchor form ``§2.F-001`` carries the entity_id and
       matches what `cataforge docs load prd#§2.F-001` consumers pass.
    2. Otherwise, exact-match on the stored `cf:source_section` literal.
    """
    import re  # noqa: PLC0415

    namespace = cf_namespace(config)
    match = re.search(r"([A-Z]+-\d{3,})", section_id)
    parsed_entity_id = match.group(1) if match else None
    if parsed_entity_id is not None:
        entity_id_lit = _sparql_lit(parsed_entity_id)
        where_clauses = f'  ?uri cf:entity_id "{entity_id_lit}" . '
    else:
        section_lit = _sparql_lit(section_id)
        where_clauses = f'  ?uri cf:source_section "{section_lit}" . '

    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?uri ?entity_id ?title ?status ?cls "
        "       ?source_doc ?source_section "
        "WHERE { "
        f"{where_clauses}"
        "  ?uri a ?cls . "
        "  OPTIONAL { ?uri cf:entity_id     ?entity_id } "
        "  OPTIONAL { ?uri cf:title         ?title } "
        "  OPTIONAL { ?uri cf:status        ?status } "
        "  OPTIONAL { ?uri cf:source_doc    ?source_doc } "
        "  OPTIONAL { ?uri cf:source_section ?source_section } "
        "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        "} LIMIT 1"
    )
    with _kg_session(config, kg=kg) as kg_inst:
        rows = list(kg_inst.store.query(sparql))
    if not rows:
        return None
    row = rows[0]
    # entity_id from the SELECT trumps the parsed fallback, but if the
    # row is missing the literal (data corruption / pre-migration row),
    # the regex-parsed ID is the next-best identifier.
    entity_id = _row_strv(row, "entity_id") or parsed_entity_id
    return {
        "uri": _row_strv(row, "uri"),
        "entity_id": entity_id,
        "title": _row_strv(row, "title"),
        "status": _row_strv(row, "status"),
        "_class": ((_row_strv(row, "cls") or "").rsplit("/", 1)[-1] or None),
        "source_doc": _row_strv(row, "source_doc"),
        "source_section": _row_strv(row, "source_section") or section_id,
        "doc_type": doc_type,
    }


def _legacy_extract(
    doc_type: str, section_id: str, project_root: str | Path
) -> dict[str, Any] | None:
    """Read the section text via the legacy file-based loader."""
    from cataforge.docs.loader import LoadSectionError
    from cataforge.docs.loader import extract as _file_extract

    ref = f"{doc_type}#{section_id}"
    try:
        body = _file_extract(ref, str(project_root))
    except LoadSectionError:
        return None
    return {
        "uri": None,
        "entity_id": None,
        "title": None,
        "status": None,
        "_class": None,
        "source_doc": doc_type,
        "source_section": section_id,
        "doc_type": doc_type,
        "body": body,
    }


# ---------------------------------------------------------------------------
# Shim 2 — extract_batch
# ---------------------------------------------------------------------------


def extract_batch(
    specs: list[dict[str, str]],
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    config: KGConfig | None = None,
    kg: KnowledgeGraph | None = None,
) -> list[dict[str, Any] | None]:
    """Batch-extract entities by a list of `{"doc_type", "section_id"}` specs.

    Dispatches per spec — a single batch can contain mixed active /
    legacy doc_types and the shim picks the correct path for each.
    """
    _emit("extract_batch", "kg.query.plan_load() or a loop over kg.query")
    cfg = _config_for(project_root, db_path=db_path, overrides=config)
    out: list[dict[str, Any] | None] = []
    for spec in specs:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            out.append(
                extract(
                    spec["doc_type"],
                    spec["section_id"],
                    project_root=project_root,
                    config=cfg,
                    kg=kg,
                )
            )
    return out


# ---------------------------------------------------------------------------
# Shim 3 — plan_load
# ---------------------------------------------------------------------------


def plan_load(
    items: list[str],
    budget: int,
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    config: KGConfig | None = None,
    kg: KnowledgeGraph | None = None,
) -> dict[str, Any]:
    """0.4.x dict-shape plan_load: ``{"ordered", "dropped", "estimated_tokens"}``.

    KG path: invokes :meth:`QueryAPI.plan_load`.

    Legacy path: delegates to :func:`cataforge.docs.loader.plan_load`,
    which works on ref strings (``prd#§2.F-001``).
    """
    _emit("plan_load", "kg.query.plan_load()")
    cfg = _config_for(project_root, db_path=db_path, overrides=config)

    kg_items: list[str] = []
    legacy_items: list[str] = []
    for item in items:
        if _active_for_item(item, cfg):
            kg_items.append(item)
        else:
            legacy_items.append(item)

    if not kg_items:
        return _legacy_plan_load(items, budget, project_root)

    if not legacy_items:
        with _kg_session(cfg, kg=kg) as kg_inst:
            result = kg_inst.query.plan_load(kg_items, budget, include_related=True)
        return {
            "ordered": result.ordered,
            "dropped": result.dropped,
            "estimated_tokens": result.estimated_tokens,
        }

    # Mixed batch: KG items go through KG planner; legacy items through
    # legacy loader. The two ordered lists are concatenated; budgeting is
    # split proportionally by item count.
    kg_share = int(budget * len(kg_items) / len(items))
    legacy_share = budget - kg_share
    with _kg_session(cfg, kg=kg) as kg_inst:
        kg_result = kg_inst.query.plan_load(kg_items, kg_share, include_related=True)
    legacy_result = _legacy_plan_load(legacy_items, legacy_share, project_root)
    return {
        "ordered": kg_result.ordered + legacy_result["ordered"],
        "dropped": kg_result.dropped + legacy_result["dropped"],
        "estimated_tokens": kg_result.estimated_tokens + legacy_result["estimated_tokens"],
    }


def _active_for_item(item: str, config: KGConfig) -> bool:
    """Return True if `item` corresponds to an active doc_type.

    For ref-form items (``doc_id#...``), the leading `doc_id` is the
    doc_type. For bare entity_ids (``F-001``), heuristic: route through
    KG when at least one active doc_type exists, since the planner
    works on entity_ids alone.
    """
    if "#" in item:
        doc_id = item.split("#", 1)[0]
        return doc_id in config.kg_active_doc_types
    return bool(config.kg_active_doc_types)


def _legacy_plan_load(items: list[str], budget: int, project_root: str | Path) -> dict[str, Any]:
    from cataforge.docs.loader import plan_load as _file_plan_load

    loadable, deferred = _file_plan_load(items, str(project_root), budget)
    return {
        "ordered": loadable,
        "dropped": deferred,
        "estimated_tokens": len(loadable) * _LEGACY_TOKEN_PER_REF,
    }


# ---------------------------------------------------------------------------
# Shim 4 — build_full_index
# ---------------------------------------------------------------------------


def build_full_index(
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    project_uri: str | None = None,
    config: KGConfig | None = None,
    kg: KnowledgeGraph | None = None,
) -> dict[str, dict[str, Any]]:
    """Build a full entity index dict keyed by entity_id.

    KG path: SPARQL SELECT over every `cf:SoftwareArtifact` ordered by
    `sort_key`.

    Legacy path: delegates to
    :func:`cataforge.docs.indexer.build_full_index` and re-shapes the
    output into the same `{entity_id: {...}}` form.
    """
    _emit("build_full_index", "kg.query.all_entities() or direct SPARQL")
    cfg = _config_for(project_root, db_path=db_path, overrides=config)
    if cfg.kg_active_doc_types:
        with _kg_session(cfg, kg=kg) as kg_inst:
            rows = kg_inst.query.all_entities()
        index: dict[str, dict[str, Any]] = {}
        for row in rows:
            eid = row.get("entity_id")
            if not eid:
                continue
            index[eid] = {
                "uri": row.get("uri"),
                "entity_id": eid,
                "title": row.get("title"),
                "status": row.get("status"),
                "sort_key": row.get("sort_key"),
                "source_doc": row.get("source_doc"),
                "source_section": row.get("source_section"),
                "_class": row.get("_class"),
            }
        return index
    return _legacy_build_full_index(project_root)


def _legacy_build_full_index(
    project_root: str | Path,
) -> dict[str, dict[str, Any]]:
    from cataforge.docs.indexer import build_full_index as _file_build

    raw = _file_build(str(project_root))
    out: dict[str, dict[str, Any]] = {}
    documents = raw.get("documents") or {}
    for doc_id, entry in documents.items():
        for section in (entry.get("sections") or {}).values():
            for item in section.get("items") or []:
                eid = item.get("id")
                if not eid:
                    continue
                out[eid] = {
                    "uri": None,
                    "entity_id": eid,
                    "title": item.get("title"),
                    "status": None,
                    "sort_key": None,
                    "source_doc": doc_id,
                    "source_section": section.get("path"),
                    "_class": None,
                }
    return out


# ---------------------------------------------------------------------------
# Shim 5 — resolve_deps
# ---------------------------------------------------------------------------


def resolve_deps(
    item_id: str,
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    config: KGConfig | None = None,
    kg: KnowledgeGraph | None = None,
) -> list[str]:
    """Direct (1-hop) dependencies for `item_id`.

    KG path: verify the entity exists in the store; if so, SPARQL over
    `cf:depends_on`. If the entity is missing from KG (reconcile drift,
    not yet ingested, or wrong-doc_type mapping) fall back to the legacy
    index so callers do not silently receive an empty deps list when the
    file-side answer still exists.

    Legacy path: delegates to
    :func:`cataforge.docs.loader.resolve_deps` which walks
    `.doc-index.json` `deps[]` entries.
    """
    _emit("resolve_deps", "kg.query.plan_load() or SPARQL `cf:depends_on`")
    cfg = _config_for(project_root, db_path=db_path, overrides=config)
    if cfg.kg_active_doc_types:
        with _kg_session(cfg, kg=kg) as kg_inst:
            if kg_inst.query.exists(item_id):
                return kg_inst.query.depends_on(item_id)
        logger.warning(
            "resolve_deps: %r absent from KG; falling back to legacy index.",
            item_id,
        )
    return _legacy_resolve_deps(item_id, project_root)


def _legacy_resolve_deps(item_id: str, project_root: str | Path) -> list[str]:
    from cataforge.docs.loader import resolve_deps as _file_resolve

    return _file_resolve(item_id, str(project_root))


# ---------------------------------------------------------------------------
# Extension shim: extract_with_body
# ---------------------------------------------------------------------------


def extract_with_body(
    doc_type: str,
    section_id: str,
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    config: KGConfig | None = None,
    kg: KnowledgeGraph | None = None,
) -> dict[str, Any] | None:
    """:func:`extract` plus a `body` key holding the rendered Markdown.

    KG path: invokes `cataforge.kg.export.render_entity()` on the
    resolved entity. Legacy path: the legacy `_legacy_extract` already
    returns the raw text in `body`.
    """
    _emit(
        "extract_with_body",
        "kg.query.entity() + cataforge.kg.export.render_entity()",
    )
    cfg = _config_for(project_root, db_path=db_path, overrides=config)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        base = extract(
            doc_type,
            section_id,
            project_root=project_root,
            config=cfg,
            kg=kg,
        )
    if base is None:
        return None
    if base.get("body") is not None:
        return base
    from cataforge.kg.export import render_entity  # noqa: PLC0415

    if not base.get("entity_id"):
        return base
    with _kg_session(cfg, kg=kg) as kg_inst:
        rendered = render_entity(kg_inst.store, base["entity_id"])
    base["body"] = rendered
    return base


# ---------------------------------------------------------------------------
# Extension shim: legacy_validate_report
# ---------------------------------------------------------------------------


def legacy_validate_report(
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    config: KGConfig | None = None,
    kg: KnowledgeGraph | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Six-key validate_docs() report shape, populated from KG when active.

    Returns the exact 0.4.x keys: `orphans`, `stale`, `xref_errors`,
    `alias_conflicts`, `invalid_ids`, `stale_deps`. The KG branch
    derives each list from SHACL + SPARQL; the legacy branch delegates
    to :func:`cataforge.docs.indexer.validate_docs`.
    """
    _emit("legacy_validate_report", "cataforge kg validate --output json")
    cfg = _config_for(project_root, db_path=db_path, overrides=config)
    if not cfg.kg_active_doc_types:
        return _legacy_validate_report(project_root)
    return _kg_validate_report(cfg, project_root=Path(project_root), kg=kg)


def _kg_validate_report(
    config: KGConfig,
    *,
    project_root: Path,
    kg: KnowledgeGraph | None = None,
) -> dict[str, list[dict[str, Any]]]:
    from cataforge.kg.reconcile import reconcile as _kg_reconcile  # noqa: PLC0415
    from cataforge.kg.validate import validate as _kg_validate  # noqa: PLC0415

    report: dict[str, list[dict[str, Any]]] = {
        "orphans": [],
        "stale": [],
        "xref_errors": [],
        "alias_conflicts": [],
        "invalid_ids": [],
        "stale_deps": [],
    }
    with _kg_session(config, kg=kg) as kg_inst:
        validation = _kg_validate(kg_inst.store, config)
        for v in validation.violations:
            entry = {"id": v.entity_id, "message": v.message}
            shape = v.shape.lower()
            if "pattern" in shape or ("entity_id" in shape and "unique" not in shape):
                report["invalid_ids"].append(entry)
            elif "unique" in shape:
                report["alias_conflicts"].append(entry)
            elif "orphan" in shape:
                report["orphans"].append(entry)
            elif "xref" in shape or "target" in shape:
                report["xref_errors"].append(entry)
            else:
                report["xref_errors"].append(entry)
        for src, dst in kg_inst.trace.stale_dependencies():
            report["stale_deps"].append({"from": src, "to": dst})
        rec = _kg_reconcile(kg_inst.store, project_root, config)
        for per in rec.per_doc_type.values():
            for entity_id in per.ghost_entities:
                report["stale"].append({"id": entity_id})
    return report


def _legacy_validate_report(
    project_root: str | Path,
) -> dict[str, list[dict[str, Any]]]:
    from cataforge.docs.indexer import validate_docs

    raw = validate_docs(str(project_root))
    out: dict[str, list[dict[str, Any]]] = {
        "orphans": [],
        "stale": [],
        "xref_errors": [],
        "alias_conflicts": [],
        "invalid_ids": [],
        "stale_deps": [],
    }
    for key in out:
        entries = raw.get(key) or []
        for e in entries:
            if isinstance(e, dict):
                out[key].append(e)
            elif isinstance(e, str):
                out[key].append({"id": e})
            elif isinstance(e, tuple) and len(e) == 2:
                out[key].append({"id": e[0], "info": e[1]})
            else:
                out[key].append({"id": str(e)})
    return out


# ---------------------------------------------------------------------------
# Extension shim: source_section
# ---------------------------------------------------------------------------


def source_section(
    doc_id: str,
    section_anchor: str,
    *,
    project_root: str | Path,
    db_path: str | Path | None = None,
    config: KGConfig | None = None,
    kg: KnowledgeGraph | None = None,
) -> str | None:
    """Raw Markdown for a section that is not modeled as an entity.

    KG path: :meth:`QueryAPI.source_section` slices the on-disk file by
    heading. Legacy path: same heading-slice operation done directly
    against the file resolved via `cataforge.docs.loader.resolve_file`.
    """
    _emit("source_section", "kg.query.source_section()")
    cfg = _config_for(project_root, db_path=db_path, overrides=config)
    if doc_id in cfg.kg_active_doc_types:
        with _kg_session(cfg, kg=kg) as kg_inst:
            return kg_inst.query.source_section(doc_id, section_anchor)
    return _legacy_source_section(doc_id, section_anchor, project_root)


def _legacy_source_section(
    doc_id: str, section_anchor: str, project_root: str | Path
) -> str | None:
    from cataforge.docs.loader import (  # noqa: PLC0415
        DocResolveError,
        resolve_file,
    )

    try:
        path = resolve_file(doc_id, str(project_root))
    except DocResolveError:
        return None
    text = Path(path).read_text(encoding="utf-8")
    return slice_section(text, section_anchor)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _row_strv(row: Any, var: str) -> str | None:
    return _strv(_row_lookup(row, var))


def _sparql_lit(value: str) -> str:
    """Backwards-compatible alias for the canonical literal escaper."""
    return escape_sparql_literal(value)


__all__ = [
    "build_full_index",
    "extract",
    "extract_batch",
    "extract_with_body",
    "legacy_validate_report",
    "plan_load",
    "resolve_deps",
    "source_section",
]
