"""Single-entity Markdown rendering.

`compile_to_markdown()` walks the whole store and writes one file per
entity. The shim layer's `extract_with_body()` needs the same render
path but for one entity at a time, without writing to disk.
`render_entity(store, entity_id, *, template=None)` provides that path.

Public symbol exposed from `cataforge.domain.kg.export` so shim callers can
import directly: `from cataforge.domain.kg.export import render_entity`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _term_value,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.export._entity_meta import (
    _RELATION_GROUPS,
    _entity_type_to_doc_type,
    resolve_template,
)
from cataforge.domain.kg.export.hydrator import hydrate_rows
from cataforge.domain.kg.export.registry import SparqlRegistry
from cataforge.domain.kg.export.template_loader import build_jinja_env

if TYPE_CHECKING:
    import pyoxigraph as ox


def _resolve_entity_type(store: ox.Store, entity_id: str, namespace: str) -> str | None:
    """Look up `entity_id`'s rdf:type and return the local class name."""
    safe_id = escape_sparql_literal(entity_id)
    sparql = (
        f"PREFIX cf: <{namespace}> "
        f"SELECT ?cls WHERE {{ "
        f'  ?s cf:entity_id "{safe_id}" ; a ?cls . '
        "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        "} LIMIT 1"
    )
    for row in select_rows(store, sparql):
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

    sparql_template = registry.get(entity_type)
    safe_id = escape_sparql_literal(entity_id)
    sparql_query = sparql_template % {"entity_id": f'"{safe_id}"'}
    raw_rows = list(select_rows(store, sparql_query))
    relation_groups = _RELATION_GROUPS.get(entity_type.lower(), {})
    context = hydrate_rows(raw_rows, relation_groups)
    if context is None:
        return None

    if jinja_env is None:
        jinja_env = build_jinja_env()
    jinja_template = resolve_template(jinja_env, entity_type, override=template)
    return str(jinja_template.render(entity=context))  # type: ignore[attr-defined]


def entity_doc_type(entity_type: str) -> str:
    """Public re-export of the entity-type → doc-type mapping.

    Used by the shim's `extract_with_body()` to choose the right
    rendering template without re-importing private pipeline helpers.
    """
    return _entity_type_to_doc_type(entity_type)


__all__ = ["entity_doc_type", "render_entity"]
