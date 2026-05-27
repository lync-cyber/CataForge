"""Store open + bootstrap + subclass closure (sub-PR 2 acceptance)."""
from __future__ import annotations

from pathlib import Path

import pytest

# --------------------------------------------------------------------------
# Memory backend — exercises the full bootstrap pipeline without disk I/O
# --------------------------------------------------------------------------

def test_init_store_memory_backend_loads_subclass_axioms() -> None:
    from cataforge.kg import KGConfig, init_store

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

def test_subclass_closure_query_returns_page_for_screen() -> None:
    """spike-2 §2.1 acceptance: `a/rdfs:subClassOf* cf:Screen` returns Page.

    Without the bootstrap triples, this would return zero results even when
    Page instances exist, because pyoxigraph performs no RDFS entailment.
    """
    import pyoxigraph as ox

    from cataforge.kg import KGConfig, init_store

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
    from cataforge.kg import KGConfig, init_store

    db = tmp_path / "kg-store"
    handle = init_store(KGConfig(store_backend="oxigraph", db_path=db))
    handle.close()

    assert db.is_dir()
    # RocksDB creates internal files on bootstrap.
    assert any(db.iterdir())

def test_init_store_refuses_overwrite_without_force(tmp_path: Path) -> None:
    from cataforge.kg import KGConfig, KGStoreAlreadyExistsError, init_store

    db = tmp_path / "kg-store"
    init_store(KGConfig(store_backend="oxigraph", db_path=db)).close()

    with pytest.raises(KGStoreAlreadyExistsError):
        init_store(KGConfig(store_backend="oxigraph", db_path=db))

def test_init_store_force_replaces_existing(tmp_path: Path) -> None:
    from cataforge.kg import KGConfig, init_store

    db = tmp_path / "kg-store"
    init_store(KGConfig(store_backend="oxigraph", db_path=db)).close()
    # Second init with --force succeeds and rebuilds.
    handle = init_store(KGConfig(store_backend="oxigraph", db_path=db), force=True)
    handle.close()
    assert db.is_dir()

def test_connect_raises_when_db_path_missing(tmp_path: Path) -> None:
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore

    db = tmp_path / "nope"
    with (
        pytest.raises(KGStoreNotInitializedError),
        KnowledgeGraphStore.connect(KGConfig(store_backend="oxigraph", db_path=db)),
    ):
        pass
