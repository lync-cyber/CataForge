"""Golden tests for the three Wave C PoC ``.md.j2`` templates.

These exercise the design's full render pipeline end-to-end against
fixture triples: parse the template, expand SPARQL parameter
substitution, run queries, apply filters, materialise the markdown.
The remaining 14 doc-gen templates will be migrated in Wave D3."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cataforge.kg.render.checker import check_render_idempotent
from cataforge.kg.render.engine import GENERATED_BY_MARKER, KGRenderer
from cataforge.kg.store import RDFLibStore, Triple

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = REPO_ROOT / ".cataforge" / "skills" / "doc-gen" / "templates" / "standard"


@pytest.fixture
def store_for_prd(tmp_path: Path) -> Iterator[RDFLibStore]:
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfk:doc/prd-acme", "rdf:type", "cfk:Document"),
        Triple("cfk:doc/prd-acme", "rdfs:label", "ACME PRD"),
        Triple("cfk:doc/prd-acme", "cfa:status", "approved"),
        # Features
        Triple("cfa:prd-acme/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd-acme/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:prd-acme/F-001", "rdfs:label", "login"),
        Triple("cfa:prd-acme/F-001", "cfk:definedIn", "cfk:doc/prd-acme"),
        Triple("cfa:prd-acme/F-002", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd-acme/F-002", "cfk:hasId", "F-002"),
        Triple("cfa:prd-acme/F-002", "rdfs:label", "signup"),
        Triple("cfa:prd-acme/F-002", "cfk:definedIn", "cfk:doc/prd-acme"),
        # NFR
        Triple("cfa:prd-acme/NFR-001", "rdf:type", "cfa:NFR"),
        Triple("cfa:prd-acme/NFR-001", "cfk:hasId", "NFR-001"),
        Triple("cfa:prd-acme/NFR-001", "rdfs:label", "login p95 < 200ms"),
        Triple("cfa:prd-acme/NFR-001", "cfk:definedIn", "cfk:doc/prd-acme"),
    ])
    yield store


@pytest.fixture
def store_for_arch(tmp_path: Path) -> Iterator[RDFLibStore]:
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfk:doc/arch-acme", "rdf:type", "cfk:Document"),
        Triple("cfk:doc/arch-acme", "rdfs:label", "ACME Arch"),
        Triple("cfa:arch-acme/M-001", "rdf:type", "cfa:Module"),
        Triple("cfa:arch-acme/M-001", "cfk:hasId", "M-001"),
        Triple("cfa:arch-acme/M-001", "rdfs:label", "auth"),
        Triple("cfa:arch-acme/M-001", "cfk:definedIn", "cfk:doc/arch-acme"),
        Triple("cfa:arch-acme/M-001", "cfa:realizes", "cfa:prd-acme/F-001"),
        Triple("cfa:prd-acme/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:arch-acme/M-002", "rdf:type", "cfa:Module"),
        Triple("cfa:arch-acme/M-002", "cfk:hasId", "M-002"),
        Triple("cfa:arch-acme/M-002", "rdfs:label", "user-store"),
        Triple("cfa:arch-acme/M-002", "cfk:definedIn", "cfk:doc/arch-acme"),
        Triple("cfa:arch-acme/M-001", "cfa:dependsOn", "cfa:arch-acme/M-002"),
        Triple("cfa:arch-acme/M-002", "cfk:hasId", "M-002"),
    ])
    yield store


@pytest.fixture
def store_for_dev_plan(tmp_path: Path) -> Iterator[RDFLibStore]:
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfk:doc/dev-plan-acme", "rdf:type", "cfk:Document"),
        Triple("cfk:doc/dev-plan-acme", "rdfs:label", "ACME Dev Plan"),
        Triple("cfa:dev-plan-acme/T-001", "rdf:type", "cfa:Task"),
        Triple("cfa:dev-plan-acme/T-001", "cfk:hasId", "T-001"),
        Triple("cfa:dev-plan-acme/T-001", "rdfs:label", "auth endpoint"),
        Triple("cfa:dev-plan-acme/T-001", "cfa:status", "active"),
        Triple("cfa:dev-plan-acme/T-001", "cfk:definedIn", "cfk:doc/dev-plan-acme"),
    ])
    yield store


def _make_renderer(store: RDFLibStore) -> KGRenderer:
    return KGRenderer(store, template_roots=[TEMPLATE_DIR])


def test_prd_template_renders_features_and_nfrs(
    store_for_prd: RDFLibStore,
) -> None:
    r = _make_renderer(store_for_prd)
    out = r.render("prd.md.j2", doc="cfk:doc/prd-acme", project="acme")
    assert "id: prd-acme" in out
    assert f"generated_by: {GENERATED_BY_MARKER}" in out
    assert "F-001: login" in out
    assert "F-002: signup" in out
    assert "NFR-001: login p95 < 200ms" in out


def test_arch_template_renders_modules_and_mermaid(
    store_for_arch: RDFLibStore,
) -> None:
    r = _make_renderer(store_for_arch)
    out = r.render("arch.md.j2", doc="cfk:doc/arch-acme", project="acme")
    assert "id: arch-acme" in out
    assert "M-001: auth" in out
    assert "M-002: user-store" in out
    # realizes traceability rendered as table
    assert "| mid | fid |" in out
    assert "| M-001 | F-001 |" in out
    # mermaid graph emitted
    assert "graph LR" in out
    assert "M_001" in out and "M_002" in out


def test_dev_plan_template_renders_tasks_table(
    store_for_dev_plan: RDFLibStore,
) -> None:
    r = _make_renderer(store_for_dev_plan)
    out = r.render(
        "dev-plan.md.j2",
        doc="cfk:doc/dev-plan-acme",
        project="acme",
    )
    assert "id: dev-plan-acme" in out
    assert "T-001" in out
    assert "auth endpoint" in out
    assert "active" in out


@pytest.mark.parametrize(
    "template,fixture_name,doc_iri,project",
    [
        ("prd.md.j2",      "store_for_prd",      "cfk:doc/prd-acme",      "acme"),
        ("arch.md.j2",     "store_for_arch",     "cfk:doc/arch-acme",     "acme"),
        ("dev-plan.md.j2", "store_for_dev_plan", "cfk:doc/dev-plan-acme", "acme"),
    ],
)
def test_template_render_twice_idempotent(
    template: str,
    fixture_name: str,
    doc_iri: str,
    project: str,
    request: pytest.FixtureRequest,
) -> None:
    store = request.getfixturevalue(fixture_name)
    r = _make_renderer(store)
    result = check_render_idempotent(
        r, template, doc=doc_iri, project=project,
    )
    assert result.is_idempotent, result.diff_preview


def test_generated_by_marker_in_every_template(
    store_for_prd: RDFLibStore,
    store_for_arch: RDFLibStore,
    store_for_dev_plan: RDFLibStore,
) -> None:
    cases = [
        ("prd.md.j2",      store_for_prd,      "cfk:doc/prd-acme"),
        ("arch.md.j2",     store_for_arch,     "cfk:doc/arch-acme"),
        ("dev-plan.md.j2", store_for_dev_plan, "cfk:doc/dev-plan-acme"),
    ]
    for tpl, store, doc_iri in cases:
        out = _make_renderer(store).render(tpl, doc=doc_iri, project="acme")
        assert GENERATED_BY_MARKER in out, f"{tpl} missing generated_by"
