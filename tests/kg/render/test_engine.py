"""Jinja2 KG renderer — globals injection, filter wiring, error paths."""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from cataforge.kg.render.engine import (
    GENERATED_BY_MARKER,
    KGRenderer,
    RenderError,
)
from cataforge.kg.store import RDFLibStore, Triple


@pytest.fixture
def store_with_features(tmp_path: Path) -> Iterator[RDFLibStore]:
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:prd/F-001", "rdfs:label", "login"),
        Triple("cfa:prd/F-002", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-002", "cfk:hasId", "F-002"),
        Triple("cfa:prd/F-002", "rdfs:label", "signup"),
    ])
    yield store


def _renderer(store: RDFLibStore, tpl_root: Path | None = None) -> KGRenderer:
    return KGRenderer(store, template_roots=[tpl_root] if tpl_root else [])


def test_render_string_inline(store_with_features: RDFLibStore) -> None:
    r = _renderer(store_with_features)
    out = r.render_string("hello {{ 'world' }}")
    assert out == "hello world"


def test_kg_query_global_executes_sparql(
    store_with_features: RDFLibStore,
) -> None:
    r = _renderer(store_with_features)
    out = r.render_string(
        "{% for row in kg.query('SELECT ?id WHERE { ?x cfk:hasId ?id } ORDER BY ?id') %}"
        "{{ row.id }};"
        "{% endfor %}",
    )
    assert out == "F-001;F-002;"


def test_kg_get_attr(store_with_features: RDFLibStore) -> None:
    r = _renderer(store_with_features)
    out = r.render_string(
        "{{ kg.get_attr('cfa:prd/F-001', 'rdfs:label') }}",
    )
    assert out == "login"


def test_kg_get_attr_missing_default(store_with_features: RDFLibStore) -> None:
    r = _renderer(store_with_features)
    out = r.render_string(
        "{{ kg.get_attr('cfa:prd/F-999', 'rdfs:label', default='(none)') }}",
    )
    assert out == "(none)"


def test_namespaces_global_exposed(store_with_features: RDFLibStore) -> None:
    r = _renderer(store_with_features)
    out = r.render_string("{{ namespaces['cfk'] }}")
    assert out == "https://cataforge.dev/ontology/kernel#"


def test_generated_by_marker_constant(store_with_features: RDFLibStore) -> None:
    r = _renderer(store_with_features)
    out = r.render_string("{{ generated_by }}")
    assert out == GENERATED_BY_MARKER


def test_bullet_list_filter_pipelines(store_with_features: RDFLibStore) -> None:
    r = _renderer(store_with_features)
    out = r.render_string(
        "{{ kg.query('SELECT ?id WHERE { ?x cfk:hasId ?id } ORDER BY ?id') "
        "| bullet_list(fmt='{id}') }}",
    )
    assert out == "- F-001\n- F-002"


def test_table_filter_pipelines(store_with_features: RDFLibStore) -> None:
    r = _renderer(store_with_features)
    out = r.render_string(
        "{{ kg.query('SELECT ?id WHERE { ?x cfk:hasId ?id } ORDER BY ?id') "
        "| table }}",
    )
    assert "| id |" in out
    assert "| F-001 |" in out


def test_kg_query_template_parameter(store_with_features: RDFLibStore) -> None:
    r = _renderer(store_with_features)
    # $iri expands to the bare CURIE; SPARQL's own { } braces don't need escaping.
    out = r.render_string(
        "{{ kg.query('ASK { $iri cfk:hasId ?id }', "
        "iri='cfa:prd/F-001')[0]['_ask'] }}",
    )
    assert out == "true"


def test_missing_template_param_raises_render_error(
    store_with_features: RDFLibStore,
) -> None:
    r = _renderer(store_with_features)
    with pytest.raises(RenderError, match="missing template parameter"):
        r.render_string("{{ kg.query('ASK { $missing ?p ?o }') }}")


def test_template_file_round_trip(
    store_with_features: RDFLibStore, tmp_path: Path,
) -> None:
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    query = (
        "SELECT ?id ?label WHERE { ?x cfk:hasId ?id ; rdfs:label ?label } "
        "ORDER BY ?id"
    )
    (tpl_dir / "features.md.j2").write_text(textwrap.dedent(f"""\
        # Features
        {{% for row in kg.query('{query}') %}}
        - {{{{ row.id }}}}: {{{{ row.label }}}}
        {{% endfor %}}
    """), encoding="utf-8")
    r = _renderer(store_with_features, tpl_root=tpl_dir)
    out = r.render("features.md.j2")
    assert "- F-001: login" in out
    assert "- F-002: signup" in out


def test_template_lookup_failure_raises(
    store_with_features: RDFLibStore, tmp_path: Path,
) -> None:
    r = _renderer(store_with_features, tpl_root=tmp_path)
    with pytest.raises(RenderError, match="failed to load template"):
        r.render("nonexistent.md.j2")


def test_strict_undefined_catches_typo(
    store_with_features: RDFLibStore,
) -> None:
    r = _renderer(store_with_features)
    with pytest.raises(RenderError):
        r.render_string("{{ undefined_global }}")
