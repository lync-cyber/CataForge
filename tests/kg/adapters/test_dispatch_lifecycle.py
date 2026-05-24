"""End-to-end dispatch cycle for every built-in adapter.

For each adapter we (1) construct it against an empty RDFLibStore, (2)
seed enough upstream data that pre_dispatch_context returns non-trivial
rows, (3) call pre_dispatch_context and assert the SPARQL params landed,
(4) feed a synthetic agent output through write_back and assert the
resulting triples carry the invocation graph IRI.

The schema files live under tmp_path so we don't depend on the bundled
.cataforge skill artifacts (those are exercised by the adapter-migrate
end-to-end test instead)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cataforge.kg.adapters import (
    DocReadAdapter,
    FeatureAuthoringAdapter,
    ModuleImplementsAdapter,
    TaskDecomposeAdapter,
    TestValidatesAdapter,
    UIRendersAdapter,
)
from cataforge.kg.store import RDFLibStore, Triple


@pytest.fixture
def store(tmp_path: Path) -> RDFLibStore:
    s = RDFLibStore()
    s.load(tmp_path)
    return s


def _write_schema(tmp_path: Path, name: str, body: dict[str, Any]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return p


# ---------- feature_authoring ----------

def test_feature_authoring_dispatch_lifecycle(
    store: RDFLibStore, tmp_path: Path,
) -> None:
    store.add([
        Triple("cfk:doc/prd-acme", "rdf:type", "cfk:Document"),
        Triple("cfa:prd-acme/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd-acme/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:prd-acme/F-001", "rdfs:label", "existing login"),
        Triple("cfa:prd-acme/F-001", "cfk:definedIn", "cfk:doc/prd-acme"),
    ])
    schema = _write_schema(tmp_path, "feature.schema.json", {
        "items": [{
            "from": "features",
            "iri": "cfa:${doc_id}/${id}",
            "type": "cfa:Feature",
            "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
            "iri_refs": {"cfk:definedIn": "cfk:doc/${doc_id}"},
        }]
    })
    config = {
        "pre_dispatch_queries": {
            "existing_features": (
                "SELECT ?id ?label WHERE {"
                "  ?f a cfa:Feature ; cfk:hasId ?id ; rdfs:label ?label ;"
                "     cfk:definedIn $doc_iri ."
                "} ORDER BY ?id"
            ),
        },
        "write_back_schema": str(schema),
    }
    adapter = FeatureAuthoringAdapter(
        store=store, invocation_id="inv-1", config=config,
    )

    ctx = adapter.pre_dispatch_context({
        "doc_id": "prd-acme",
        "doc_iri": "cfk:doc/prd-acme",
    })
    assert ctx["existing_features"] == [{"id": "F-001", "label": "existing login"}]

    new_triples = adapter.write_back({
        "doc_id": "prd-acme",
        "features": [
            {"id": "F-002", "label": "Logout"},
        ],
    })
    assert Triple(
        "cfa:prd-acme/F-002", "cfk:definedIn", "cfk:doc/prd-acme",
    ) in new_triples
    # Triples actually landed in the store on the invocation graph.
    quads = [
        (s, p, o, g) for s, p, o, g in store
        if s.endswith("prd-acme/F-002")
    ]
    assert quads
    invocation_graphs = {g for _, _, _, g in quads if g is not None}
    assert any("invocation/inv-1" in g for g in invocation_graphs)


# ---------- module_implements ----------

def test_module_implements_creates_edges(
    store: RDFLibStore, tmp_path: Path,
) -> None:
    store.add([
        Triple("cfa:prd-acme/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd-acme/F-001", "cfk:hasId", "F-001"),
    ])
    schema = _write_schema(tmp_path, "module.schema.json", {
        "items": [{
            "from": "modules",
            "iri": "cfa:${doc_id}/${id}",
            "type": "cfa:Module",
            "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
            "iri_refs": {
                "cfa:implements": {"field": "implements", "as_iri": True},
            },
        }]
    })
    adapter = ModuleImplementsAdapter(
        store=store, invocation_id="inv-2",
        config={
            "pre_dispatch_queries": {},
            "write_back_schema": str(schema),
        },
    )
    triples = adapter.write_back({
        "doc_id": "arch-acme",
        "modules": [{
            "id": "M-001", "label": "auth",
            "implements": ["cfa:prd-acme/F-001"],
        }],
    })
    assert Triple(
        "cfa:arch-acme/M-001", "cfa:implements", "cfa:prd-acme/F-001",
    ) in triples
    quads = [(s, p, o, g) for s, p, o, g in store if s.endswith("arch-acme/M-001")]
    assert quads, "M-001 triples must be persisted in the store"
    assert any("invocation/inv-2" in g for _, _, _, g in quads if g is not None)


# ---------- task_decompose ----------

def test_task_decompose_basic(store: RDFLibStore, tmp_path: Path) -> None:
    schema = _write_schema(tmp_path, "task.schema.json", {
        "items": [{
            "from": "tasks",
            "iri": "cfa:${doc_id}/${id}",
            "type": "cfa:Task",
            "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
            "iri_refs": {
                "cfa:decomposes": {"field": "decomposes", "as_iri": True},
            },
        }]
    })
    adapter = TaskDecomposeAdapter(
        store=store, invocation_id="inv-3",
        config={
            "pre_dispatch_queries": {},
            "write_back_schema": str(schema),
        },
    )
    triples = adapter.write_back({
        "doc_id": "dev-plan-acme",
        "tasks": [{
            "id": "T-001", "label": "implement login",
            "decomposes": "cfa:arch-acme/M-001",
        }],
    })
    assert Triple(
        "cfa:dev-plan-acme/T-001", "cfa:decomposes", "cfa:arch-acme/M-001",
    ) in triples
    quads = [(s, p, o, g) for s, p, o, g in store if s.endswith("dev-plan-acme/T-001")]
    assert quads, "T-001 triples must be persisted in the store"
    assert any("invocation/inv-3" in g for _, _, _, g in quads if g is not None)


# ---------- test_validates ----------

def test_test_validates_basic(store: RDFLibStore, tmp_path: Path) -> None:
    schema = _write_schema(tmp_path, "test.schema.json", {
        "items": [{
            "from": "test_cases",
            "iri": "cfa:${doc_id}/${id}",
            "type": "cfa:TestCase",
            "literals": {"cfk:hasId": "id"},
            "iri_refs": {
                "cfa:validates": {"field": "validates", "as_iri": True},
            },
        }]
    })
    adapter = TestValidatesAdapter(
        store=store, invocation_id="inv-4",
        config={
            "pre_dispatch_queries": {},
            "write_back_schema": str(schema),
        },
    )
    triples = adapter.write_back({
        "doc_id": "test-plan",
        "test_cases": [{
            "id": "TC-001",
            "validates": "cfa:prd-acme/F-001",
        }],
    })
    assert Triple(
        "cfa:test-plan/TC-001", "cfa:validates", "cfa:prd-acme/F-001",
    ) in triples
    quads = [(s, p, o, g) for s, p, o, g in store if s.endswith("test-plan/TC-001")]
    assert quads, "TC-001 triples must be persisted in the store"
    assert any("invocation/inv-4" in g for _, _, _, g in quads if g is not None)


# ---------- doc_read ----------

def test_doc_read_ignores_write_back(store: RDFLibStore) -> None:
    store.add([
        Triple("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-001", "cfk:hasId", "F-001"),
    ])
    adapter = DocReadAdapter(
        store=store, invocation_id="inv-5",
        config={
            "pre_dispatch_queries": {
                "all_features": (
                    "SELECT ?id WHERE {"
                    " ?f a cfa:Feature ; cfk:hasId ?id"
                    "} ORDER BY ?id"
                ),
            },
        },
    )
    ctx = adapter.pre_dispatch_context({})
    assert ctx["all_features"] == [{"id": "F-001"}]

    # Even if the agent emits structured output, write_back is a no-op.
    triples_before = len(list(store))
    triples = adapter.write_back({"features": [{"id": "F-999"}]})
    assert triples == []
    assert len(list(store)) == triples_before


# ---------- ui_renders ----------

def test_ui_renders_basic(store: RDFLibStore, tmp_path: Path) -> None:
    schema = _write_schema(tmp_path, "ui.schema.json", {
        "items": [{
            "from": "components",
            "iri": "cfa:${doc_id}/${id}",
            "type": "cfa:Component",
            "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
            "iri_refs": {
                "cfa:renders": {"field": "renders", "as_iri": True},
            },
        }]
    })
    adapter = UIRendersAdapter(
        store=store, invocation_id="inv-6",
        config={
            "pre_dispatch_queries": {},
            "write_back_schema": str(schema),
        },
    )
    triples = adapter.write_back({
        "doc_id": "ui-spec-acme",
        "components": [{
            "id": "C-001", "label": "LoginForm",
            "renders": ["cfa:prd-acme/F-001"],
        }],
    })
    assert Triple(
        "cfa:ui-spec-acme/C-001", "cfa:renders", "cfa:prd-acme/F-001",
    ) in triples
    quads = [(s, p, o, g) for s, p, o, g in store if s.endswith("ui-spec-acme/C-001")]
    assert quads, "C-001 triples must be persisted in the store"
    assert any("invocation/inv-6" in g for _, _, _, g in quads if g is not None)


# ---------- generic invariants ----------

def test_invocation_graph_iri_format(store: RDFLibStore) -> None:
    adapter = DocReadAdapter(
        store=store, invocation_id="abc-123",
        config={"pre_dispatch_queries": {}},
    )
    assert adapter.invocation_graph_iri() == "cfk:invocation/abc-123"
