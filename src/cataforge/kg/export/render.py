"""Single-entity Markdown rendering — task-5 errata C2.

`compile_to_markdown()` walks the whole store and writes one file per
entity. The shim layer's `extract_with_body()` (Task 6 §6.5 #1) needs
the same render path but for one entity at a time, without writing to
disk. `render_entity(store, entity_id, *, template=None)` is that
extraction.

Public symbol exposed from `cataforge.kg.export` so shim callers can
import directly: `from cataforge.kg.export import render_entity`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from cataforge.kg._sparql_utils import _row_lookup, _term_value
from cataforge.kg.export.hydrator import hydrate_rows
from cataforge.kg.export.pipeline import (
    _RELATION_GROUPS,
    _entity_type_to_doc_type,
    _template_name,
)
from cataforge.kg.export.registry import SparqlRegistry
from cataforge.kg.export.template_loader import build_jinja_env

if TYPE_CHECKING:
    import pyoxigraph as ox


def _resolve_entity_type(store: ox.Store, entity_id: str, namespace: str) -> str | None:
    """Look up `entity_id`'s rdf:type and return the local class name."""
    sparql = (
        f"PREFIX cf: <{namespace}> "
        f"SELECT ?cls WHERE {{ "
        f'  ?s cf:entity_id "{entity_id}" ; a ?cls . '
        "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        "} LIMIT 1"
    )
    for row in store.query(sparql):
        cls = _term_value(_row_lookup(row, "cls"))
        if cls is not None:
            return str(cls).rsplit("/", 1)[-1]
    return None


def render_entity(
    store: ox.Store,
    entity_id: str,
    *,
    template: str | None = None,
    namespace: str = "https://cataforge.dev/ontology/",
    registry: SparqlRegistry | None = None,
    jinja_env: object | None = None,
) -> str | None:
    """Render ``entity_id`` to Markdown using the registered Jinja template.

    Parameters
    ----------
    store:
        Open ``pyoxigraph.Store``.
    entity_id:
        Frontmatter ID such as ``"F-001"``.
    template:
        Optional override of the auto-resolved template path.
    namespace:
        Ontology namespace.
    registry:
        Pre-built ``SparqlRegistry``. Built on each call when ``None``.
    jinja_env:
        Pre-built Jinja2 ``Environment``. Built on each call when ``None``.
    """
    namespace = namespace.rstrip("/") + "/"
    entity_type = _resolve_entity_type(store, entity_id, namespace)
    if entity_type is None:
        return None

    if registry is None:
        registry = SparqlRegistry()
    if not registry.has(entity_type):
        return None

    sparql_template = registry.get(entity_type)
    safe_id = entity_id.replace("\\", "\\\\").replace('"', '\\"')
    sparql_query = sparql_template % {"entity_id": f'"{safe_id}"'}
    raw_rows = list(store.query(sparql_query))
    relation_groups = _RELATION_GROUPS.get(entity_type.lower(), {})
    context = hydrate_rows(raw_rows, relation_groups)
    if context is None:
        return None

    if jinja_env is None:
        jinja_env = build_jinja_env()
    tpl_name = template or _template_name(entity_type)
    jinja_template = jinja_env.get_template(tpl_name)  # type: ignore[union-attr]
    return jinja_template.render(entity=context)


def entity_doc_type(entity_type: str) -> str:
    """Public re-export of the entity-type → doc-type mapping.

    Used by the shim's `extract_with_body()` to choose the right
    rendering template without re-importing private pipeline helpers.
    """
    return _entity_type_to_doc_type(entity_type)


__all__ = ["entity_doc_type", "render_entity"]
