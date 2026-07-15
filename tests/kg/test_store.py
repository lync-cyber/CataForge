"""Store open + bootstrap + subclass closure (sub-PR 2 acceptance)."""

from __future__ import annotations

from pathlib import Path

import pytest

# --------------------------------------------------------------------------
# Memory backend — exercises the full bootstrap pipeline without disk I/O
# --------------------------------------------------------------------------


def test_init_store_memory_backend_loads_subclass_axioms() -> None:
    from cataforge.domain.kg import KGConfig, init_store

    config = KGConfig(store_backend="memory")
    handle = init_store(config)

    triples = list(handle.raw.quads_for_pattern(None, None, None, None))
    assert len(triples) > 0, "bootstrap inserted zero rdfs:subClassOf triples"

    # Verify the well-known is_a chains from spike-2 §2.1 are materialized.
    assert handle.ask(
        "ASK { <https://cataforge.dev/ontology/Feature> "
        "<http://www.w3.org/2000/01/rdf-schema#subClassOf> "
        "<https://cataforge.dev/ontology/Requirement> }"
    )
    assert handle.ask(
        "ASK { <https://cataforge.dev/ontology/Page> "
        "<http://www.w3.org/2000/01/rdf-schema#subClassOf> "
        "<https://cataforge.dev/ontology/Screen> }"
    )


def test_bootstrap_requires_no_linkml_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Store bootstrap works from the packaged axioms artifact alone.

    The published wheel's runtime dependencies exclude the linkml stack, so
    `kg init` must never import it: blocking the import proves the bootstrap
    path reads `_generated/subclass_axioms.ttl` instead of walking schemas.
    """
    import sys

    blocked = {m for m in sys.modules if m.split(".", 1)[0] == "linkml_runtime"}
    for name in blocked | {"linkml_runtime"}:
        monkeypatch.setitem(sys.modules, name, None)

    from cataforge.domain.kg import KGConfig, init_store

    handle = init_store(KGConfig(store_backend="memory"))
    assert handle.ask(
        "ASK { <https://cataforge.dev/ontology/Feature> "
        "<http://www.w3.org/2000/01/rdf-schema#subClassOf> "
        "<https://cataforge.dev/ontology/Requirement> }"
    )


@pytest.mark.parametrize("include_governance", [False, True])
def test_bootstrap_axioms_match_schema_walk(include_governance: bool) -> None:
    """Packaged-artifact bootstrap inserts exactly the axioms the LinkML walk yields."""
    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._schema_axioms import (
        expand_curie,
        iter_subclass_axioms,
        prefix_map,
    )

    prefixes = prefix_map(include_governance=include_governance)
    expected = {
        (expand_curie(child, prefixes), expand_curie(parent, prefixes))
        for child, parent in iter_subclass_axioms(include_governance=include_governance)
    }
    assert expected, "schema walk yielded zero axioms — fixture assumptions broken"

    handle = init_store(KGConfig(store_backend="memory", governance=include_governance))
    subclassof = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf")
    actual = {
        (quad.subject.value, quad.object.value)
        for quad in handle.raw.quads_for_pattern(None, subclassof, None, None)
    }
    assert actual == expected


def test_subclass_closure_query_returns_page_for_screen() -> None:
    """spike-2 §2.1 acceptance: `a/rdfs:subClassOf* cf:Screen` returns Page.

    Without the bootstrap triples, this would return zero results even when
    Page instances exist, because pyoxigraph performs no RDFS entailment.
    """
    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig, init_store

    config = KGConfig(store_backend="memory")
    handle = init_store(config)

    # Insert a concrete Page instance to prove the closure works on data,
    # not just on the class hierarchy alone.
    page_iri = ox.NamedNode("https://cataforge.dev/instance/P-001")
    page_class = ox.NamedNode("https://cataforge.dev/ontology/Page")
    rdf_type = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    handle.raw.add(ox.Quad(page_iri, rdf_type, page_class))

    results = list(
        handle.raw.query(
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?s WHERE { ?s a/rdfs:subClassOf* cf:Screen }"
        )
    )
    assert results, "subclass-closure query returned zero rows for cf:Screen"
    matched_iris = {str(row["s"].value) for row in results}
    assert "https://cataforge.dev/instance/P-001" in matched_iris


# --------------------------------------------------------------------------
# Oxigraph backend — exercises disk lifecycle
# --------------------------------------------------------------------------


def test_init_store_oxigraph_backend_creates_db_path(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store

    db = tmp_path / "kg-store"
    handle = init_store(KGConfig(store_backend="oxigraph", db_path=db))
    handle.close()

    assert db.is_dir()
    # RocksDB creates internal files on bootstrap.
    assert any(db.iterdir())


def test_init_store_refuses_overwrite_without_force(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, KGStoreAlreadyExistsError, init_store

    db = tmp_path / "kg-store"
    init_store(KGConfig(store_backend="oxigraph", db_path=db)).close()

    with pytest.raises(KGStoreAlreadyExistsError):
        init_store(KGConfig(store_backend="oxigraph", db_path=db))


def test_init_store_force_replaces_existing(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store

    db = tmp_path / "kg-store"
    init_store(KGConfig(store_backend="oxigraph", db_path=db)).close()
    # Second init with --force succeeds and rebuilds.
    handle = init_store(KGConfig(store_backend="oxigraph", db_path=db), force=True)
    handle.close()
    assert db.is_dir()


def test_connect_raises_when_db_path_missing(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore

    db = tmp_path / "nope"
    with (
        pytest.raises(KGStoreNotInitializedError),
        KnowledgeGraphStore.connect(KGConfig(store_backend="oxigraph", db_path=db)),
    ):
        pass


# RocksDB files the OS mutates independently of store content (LOCK is even
# unreadable on Windows while the store is open). They carry no graph state, so
# the content fingerprint skips them.
_VOLATILE_STORE_FILES = {"LOCK", "LOG", "IDENTITY"}


def _is_stable_store_file(name: str) -> bool:
    return name not in _VOLATILE_STORE_FILES and not name.startswith("LOG.old.")


def _store_fingerprint(db: Path) -> dict[str, bytes]:
    """Map of relative-path -> bytes for every content-bearing file under *db*."""
    return {
        str(p.relative_to(db)): p.read_bytes()
        for p in sorted(db.rglob("*"))
        if p.is_file() and _is_stable_store_file(p.name)
    }


def test_read_only_connect_leaves_store_dir_byte_identical(tmp_path: Path) -> None:
    """A read-only open performs no manifest/WAL/CURRENT rotation.

    Query-only callers (`context read`, snapshot creation) must not mutate the
    store: rotation on open would make snapshots non-deterministic and churn
    the on-disk cache for no reason.
    """
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store

    db = tmp_path / "kg-store"
    config = KGConfig(store_backend="oxigraph", db_path=db)
    handle = init_store(config)
    handle.raw.flush()
    handle.raw.optimize()
    handle.close()

    before = _store_fingerprint(db)
    with KnowledgeGraph.connect(config, read_only=True) as kg:
        kg.query.entity_ids()  # exercise a real read through the store

    assert _store_fingerprint(db) == before


def test_read_only_open_returns_persisted_data(tmp_path: Path) -> None:
    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore, init_store

    db = tmp_path / "kg-store"
    config = KGConfig(store_backend="oxigraph", db_path=db)
    handle = init_store(config)
    quad = ox.Quad(
        ox.NamedNode("https://cataforge.dev/instance/F-001"),
        ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
        ox.NamedNode("https://cataforge.dev/ontology/Feature"),
    )
    handle.raw.add(quad)
    handle.raw.flush()
    handle.close()

    with KnowledgeGraphStore.connect(config, read_only=True) as ro:
        assert quad in set(ro.raw.quads_for_pattern(None, None, None, None))
