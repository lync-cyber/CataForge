"""KG-bridge helpers for :mod:`cataforge.domain.docs.loader`.

Each public ``extract`` / ``plan_load`` / ``resolve_deps`` entry point first
asks these ``_try_kg_*`` helpers whether the project's KG can satisfy the
request (the doc_type is active and the entity is present); a ``None`` return
means "fall through to the legacy file/index path". KG access is imported
lazily so the docs layer never hard-depends on the kg subsystem — a project
without the optional KG store keeps working on the legacy path.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

from cataforge.domain.docs.index_ops import LoadSectionError, parse_ref

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cataforge.domain.docs.kg_port import KGReadPort

_SECTION_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _anchor_section_number(anchor: str) -> str | None:
    """Return the leading numeric path of a section anchor, e.g.

    ``"§2.1 F-001 用户登录"`` → ``"2.1"``; ``None`` when the heading is
    not numbered. Mirrors how refs address sections (``doc#§2.1``).
    """
    head = anchor.lstrip("§ \t")
    token = head.split(maxsplit=1)[0] if head.split() else ""
    return token if _SECTION_NUMBER_RE.match(token) else None


def _try_kg_extract(
    doc_id: str,
    section_path: str,
    item_id: str | None,
    project_root: str,
) -> str | None:
    """Resolve a ref through the KG when active.

    Entity refs (`item_id` present) render through the entity template;
    whole-section refs (`item_id is None`) resolve the matching Section
    node and return its `narrative_body`. Either way a `None` return
    signals "fall through to the legacy file path". An entity card that
    carries neither a source narrative nor child-entity content is
    declined the same way — the raw file slice is strictly more
    informative than a links-only card. Never raises — KG failures
    during a read always degrade to legacy behavior so the cutover gate
    stays a soft fence at the read layer (the doctor
    `kg_ingestion_completeness` gate enforces hard completeness at
    deploy time).
    """
    try:
        from cataforge.domain.kg._dispatch import is_active_for, kg_config_for
    except ImportError:
        return None
    if not is_active_for(doc_id, project_root):
        return None
    try:
        from cataforge.domain.kg import KnowledgeGraph
        from cataforge.domain.kg.export import render_entity_card
    except ImportError:
        return None
    cfg = kg_config_for(project_root)
    try:
        with KnowledgeGraph.connect(cfg) as kg:
            if item_id is None:
                return _kg_section_body(kg.store, cfg, doc_id, section_path)
            if not kg.query.exists(item_id):
                return None
            card = render_entity_card(kg.store, item_id)
    except Exception as exc:
        logger.debug("KG extract fallback for %r/%r: %s", doc_id, item_id, exc)
        return None
    if card is None or not (card.has_narrative or card.has_children):
        return None
    return card.markdown if card.markdown else None


def _kg_section_body(store: Any, cfg: Any, doc_id: str, section_path: str) -> str | None:
    """Return the `narrative_body` of the Section in `doc_id` whose anchor's
    numeric path equals `section_path`, or `None` to fall back to file."""
    from cataforge.domain.kg._sparql_utils import cf_namespace, escape_sparql_literal

    ns = cf_namespace(cfg)
    safe_doc = escape_sparql_literal(doc_id)
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT ?anchor ?body WHERE { "
        "  ?s a cf:Section ; "
        f'     cf:source_doc "{safe_doc}" ; '
        "     cf:section_anchor ?anchor ; "
        "     cf:narrative_body ?body . "
        "}"
    )
    for row in store.query(sparql):
        anchor = row["anchor"]
        body = row["body"]
        if anchor is None or body is None:
            continue
        if _anchor_section_number(str(anchor.value)) == section_path:
            return str(body.value) or None
    return None


def _try_kg_plan_load(
    refs: list[str], project_root: str, token_budget: int
) -> tuple[list[str], list[str]] | None:
    """KG-backed ``plan_load`` when every ref targets an active doc_type.

    Returns ``(loadable, deferred)`` ref-form tuples, or ``None`` to signal
    "fall through to legacy". The fall-through criteria are deliberately
    strict — mixed active+legacy inputs go to legacy because budget math
    over heterogeneous sources is not well-defined.
    """
    parsed = _all_active_parsed_refs(refs, project_root)
    if parsed is None:
        return None
    if not parsed:
        # empty input — legacy returns ([], []), match that without touching KG
        return [], []
    try:
        from cataforge.domain.kg import KnowledgeGraph  # noqa: PLC0415
        from cataforge.domain.kg._dispatch import kg_config_for  # noqa: PLC0415
    except ImportError:
        return None

    item_ids = [item_id for _ref, _doc_id, item_id in parsed]
    cfg = kg_config_for(project_root)
    try:
        with KnowledgeGraph.connect(cfg) as kg:
            result = kg.query.plan_load(item_ids, token_budget, include_related=False)
    except Exception as exc:
        logger.debug("KG plan_load fallback for %d items: %s", len(item_ids), exc)
        return None

    by_eid = {item_id: ref for ref, _doc_id, item_id in parsed}
    loadable = [by_eid[eid] for eid in result.ordered if eid in by_eid]
    deferred = [by_eid[eid] for eid in result.dropped if eid in by_eid]
    return loadable, deferred


def _try_kg_resolve_deps(ref: str, project_root: str, max_depth: int) -> list[str] | None:
    """KG-backed ``resolve_deps`` returning legacy ref-form list.

    Walks ``cf:depends_on`` transitively up to ``max_depth`` from the
    ref's entity_id, then reconstructs each dep's ref form from KG's
    stored ``source_doc`` / ``source_section`` slots. Returns ``None`` to
    fall through to the legacy ``.doc-index.json`` walk.
    """
    try:
        doc_id, _section, item_id = parse_ref(ref)
    except LoadSectionError:
        return None
    if item_id is None:
        return None  # whole-section refs have no entity to walk
    try:
        from cataforge.domain.kg._dispatch import is_active_for  # noqa: PLC0415
    except ImportError:
        return None
    if not is_active_for(doc_id, project_root):
        return None
    try:
        from cataforge.domain.kg import KnowledgeGraph  # noqa: PLC0415
        from cataforge.domain.kg._dispatch import kg_config_for  # noqa: PLC0415
    except ImportError:
        return None

    cfg = kg_config_for(project_root)
    try:
        with KnowledgeGraph.connect(cfg) as kg:
            visited: set[str] = {item_id}
            ordered: list[str] = []

            def _walk(eid: str, depth: int) -> None:
                if depth > max_depth:
                    return
                for dep_id in kg.query.depends_on(eid):
                    if dep_id in visited:
                        continue
                    visited.add(dep_id)
                    _walk(dep_id, depth + 1)
                    ordered.append(dep_id)

            _walk(item_id, 0)
            return [_entity_id_to_ref(cast("KGReadPort", kg), eid) or eid for eid in ordered]
    except Exception as exc:
        logger.debug("KG resolve_deps fallback for %r: %s", item_id, exc)
        return None


def _entity_id_to_ref(kg: KGReadPort, entity_id: str) -> str | None:
    """Reconstruct the legacy ``doc_id#§section`` form from KG metadata.

    Falls back to ``None`` when KG carries no ``source_doc`` for the
    entity — caller substitutes the bare entity_id, which keeps the dep
    visible in CLI output even if it won't round-trip through ``extract``.
    """
    entity = kg.query.entity(entity_id)
    if not entity:
        return None
    source_doc = entity.get("source_doc")
    if not source_doc:
        return None
    source_section = entity.get("source_section") or ""
    anchor = source_section.lstrip("§").strip()
    return f"{source_doc}#§{anchor}" if anchor else f"{source_doc}#§{entity_id}"


def _all_active_parsed_refs(
    refs: list[str], project_root: str
) -> list[tuple[str, str, str]] | None:
    """Pre-parse refs and verify every one targets an active doc_type.

    Returns ``[(ref, doc_id, item_id), ...]`` when all refs parse cleanly
    AND every ``doc_id`` is in ``kg_active_doc_types`` AND every ref
    carries an ``item_id`` (whole-section refs have no entity to plan).
    Returns ``None`` to signal "fall through to legacy".
    """
    try:
        from cataforge.domain.kg._dispatch import active_doc_types  # noqa: PLC0415
    except ImportError:
        return None
    active = active_doc_types(project_root)
    if not active:
        return None
    parsed: list[tuple[str, str, str]] = []
    for ref in refs:
        try:
            doc_id, _section, item_id = parse_ref(ref)
        except LoadSectionError:
            return None
        if doc_id not in active or item_id is None:
            return None
        parsed.append((ref, doc_id, item_id))
    return parsed
