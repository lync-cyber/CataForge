"""Wave B4 — dogfood-style end-to-end round-trip.

Exercises the full ingest → migrate → delta → apply → validate pipeline
on a synthetic three-document project (PRD / Arch / Test), the way a
real user touching markdown would drive it.

This is an integration test of the KG components, not an install-path
test — it uses the in-process Python API. The wheel-install e2e suite
under ``tests/e2e/`` covers the user-facing CLI separately."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cataforge.kg.benchmark import DEFAULT_BUDGET, run_benchmarks
from cataforge.kg.delta import apply, compute_delta
from cataforge.kg.ingest.markdown import ingest_markdown
from cataforge.kg.migrate import migrate
from cataforge.kg.ontology import load_shapes
from cataforge.kg.reasoning import validate as reasoning_validate
from cataforge.kg.store import (
    INFERRED_GRAPH_IRI,
    INSTANCES_FILENAME,
    RDFLibStore,
    Triple,
    graph_dir_for,
)


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


@pytest.fixture
def three_doc_project(tmp_path: Path) -> Path:
    """A minimal PRD + Arch + Test layout the migrator can ingest.

    The cross-doc relations are real: Arch's M-001 realizes PRD's F-001,
    and the TestCase validates PRD's F-001 — so a successful round-trip
    must keep both edges intact after the file edit."""
    _write(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        doc_type: prd
        ---
        # PRD-X

        ## F-001 用户登录
        Body.
        """)
    _write(tmp_path, "docs/arch.md", """\
        ---
        id: arch-x
        doc_type: arch
        realizes: F-001
        ---
        # Arch-X

        ## M-001 auth module
        """)
    _write(tmp_path, "docs/test.md", """\
        ---
        id: test-x
        doc_type: test
        validates: F-001
        ---
        # Test-X

        ## TC-001 login happy path
        """)
    return tmp_path


def test_migrate_persists_and_resolves_cross_doc(
    three_doc_project: Path,
) -> None:
    report = migrate(three_doc_project, validate=False)
    assert report.files_processed == 3
    assert (graph_dir_for(three_doc_project) / INSTANCES_FILENAME).is_file()

    store = RDFLibStore()
    store.load(three_doc_project)
    rows = store.query(
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "SELECT ?s ?o WHERE { ?s cfa:realizes ?o } ORDER BY ?s",
    )
    # Frontmatter `realizes: F-001` on arch.md → arch-doc → prd-x/F-001
    assert any(r["o"].endswith("prd-x/F-001") for r in rows)


def test_edit_then_delta_apply_validates(
    three_doc_project: Path,
) -> None:
    migrate(three_doc_project, validate=False)

    # Author adds F-002 inside the PRD.
    _write(three_doc_project, "docs/prd.md", """\
        ---
        id: prd-x
        doc_type: prd
        ---
        # PRD-X

        ## F-001 用户登录
        ## F-002 用户注册
        """)

    # Re-ingest just that one doc and diff against the current KG.
    store = RDFLibStore()
    store.load(three_doc_project)
    kg_triples = [_curie_triple(s, p, o) for s, p, o, _ in store]

    result = ingest_markdown(
        three_doc_project / "docs" / "prd.md",
        project_root=three_doc_project,
    )
    assert result.document is not None
    scope = {result.document.iri} | {it.iri for it in result.items}

    delta = compute_delta(
        kg_triples, result.triples, subject_scope=scope,
    )
    # The body edit changes cfk:contentHash — file is authoritative for its
    # own hash, so this is a textbook file-wins resolution.
    assert all(c.predicate == "cfk:contentHash" for c in delta.conflicts)
    assert any(
        t.s.endswith("prd-x/F-002") and t.p == "rdf:type"
        for t in delta.additions
    )

    apply(delta, store, strategy="file-wins")
    store.persist()

    # F-002 must now be queryable.
    rows = store.query(
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "ASK { ?x a cfa:Feature . ?x <https://cataforge.dev/ontology/kernel#hasId> 'F-002' }",
    )
    assert rows == [{"_ask": "true"}]

    # SHACL should still validate (the added feature has hasId + label).
    shapes = load_shapes(three_doc_project, include_l3=True, strict=True)
    shapes_tmp = graph_dir_for(three_doc_project) / "_shapes.tmp.ttl"
    shapes.serialize(destination=str(shapes_tmp), format="turtle")
    try:
        vr = reasoning_validate(store, shape_graph=shapes_tmp)
    finally:
        shapes_tmp.unlink(missing_ok=True)
    assert vr.conforms, vr.results_text


def test_idempotent_repeat_ingest_produces_empty_delta(
    three_doc_project: Path,
) -> None:
    migrate(three_doc_project, validate=False)
    store = RDFLibStore()
    store.load(three_doc_project)
    kg_triples = [
        _curie_triple(s, p, o)
        for s, p, o, g in store
        if g != INFERRED_GRAPH_IRI
    ]

    result = ingest_markdown(
        three_doc_project / "docs" / "prd.md",
        project_root=three_doc_project,
    )
    assert result.document is not None
    scope = {result.document.iri} | {it.iri for it in result.items}
    delta = compute_delta(
        kg_triples, result.triples, subject_scope=scope,
    )
    assert delta.is_clean, delta.format()


def test_full_rebuild_within_budget(three_doc_project: Path) -> None:
    """Sanity check that the bench harness runs against a real project."""
    results = run_benchmarks(three_doc_project, budget=DEFAULT_BUDGET)
    full = next((r for r in results if r.name == "full_rebuild"), None)
    assert full is not None
    # WARN is allowed; smoke-test the status surface only.
    assert full.status in {"OK", "WARN"}
    # Hard upper bound: catastrophic hangs must never pass silently.
    assert full.elapsed_ms < 60_000, f"full_rebuild took {full.elapsed_ms:.0f}ms — runaway"


def test_rollback_restores_pre_migration_state(
    three_doc_project: Path,
) -> None:
    migrate(three_doc_project, validate=False)
    first_count = _store_triple_count(three_doc_project)

    # Author mutation: drop the entire PRD file (extreme edit).
    (three_doc_project / "docs" / "prd.md").unlink()
    migrate(three_doc_project, validate=False)
    second_count = _store_triple_count(three_doc_project)
    assert second_count < first_count

    # Rollback should bring back the larger graph.
    migrate(three_doc_project, rollback=True, validate=False)
    restored = _store_triple_count(three_doc_project)
    assert restored == first_count


_PREFIX_MAP = {
    "https://cataforge.dev/ontology/kernel#":   "cfk:",
    "https://cataforge.dev/ontology/process#":  "cfp:",
    "https://cataforge.dev/ontology/artifact#": "cfa:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://www.w3.org/2000/01/rdf-schema#":       "rdfs:",
    "http://purl.org/dc/terms/":                   "dct:",
}


def _shorten(iri: str) -> str:
    for prefix, short in _PREFIX_MAP.items():
        if iri.startswith(prefix):
            return short + iri[len(prefix):]
    return iri


def _curie_triple(s: str, p: str, o: str) -> Triple:
    return Triple(s=_shorten(s), p=_shorten(p), o=_shorten(o))


def _store_triple_count(root: Path) -> int:
    store = RDFLibStore()
    store.load(root)
    return len(store)
