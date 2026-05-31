"""Regression tests for the KG-domain baseline-hardening fixes.

Each test fails against the pre-fix code: the always-true render guard, the
ingest/export doc_type gap, the unguarded ASK-injection helper, the
non-restoring transaction commit, and the silently-suppressed ghost restore.
"""

from __future__ import annotations

import pytest


def test_sparql_registry_has_no_dead_guard_and_get_falls_back_to_generic() -> None:
    """The removed ``has()`` always returned True; ``get()`` already covers
    every class via the generic template, so rendering an unregistered type
    must not be gated."""
    from cataforge.domain.kg.export._entity_meta import GENERIC_SPARQL_KEY
    from cataforge.domain.kg.export.registry import SparqlRegistry

    reg = SparqlRegistry()
    assert not hasattr(reg, "has")
    assert reg.get("CompletelyUnknownType") == reg.get(GENERIC_SPARQL_KEY)


def test_every_ingest_class_has_an_export_doc_type() -> None:
    """Every class the importer can mint must have an explicit export
    doc_type, so none silently lands in misc/ where drift detection misses it.
    """
    from cataforge.domain.kg.export._entity_meta import _ENTITY_TYPE_TO_DOC_TYPE
    from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS

    unmapped = set(ENTITY_PREFIX_TO_CLASS.values()) - set(_ENTITY_TYPE_TO_DOC_TYPE)
    assert not unmapped, f"ingest classes with no export doc_type (would fall to misc/): {unmapped}"


def test_triple_exists_rejects_unsafe_iri() -> None:
    """``_triple_exists`` guards its IRIs like its sibling helpers do."""
    from cataforge.domain.kg.ingest.writer import _triple_exists

    with pytest.raises(ValueError):
        _triple_exists(None, "subject>injection", "p", "o")


def test_commit_restores_removed_quads_on_add_failure() -> None:
    """A mid-commit add failure must not leave the removed quads gone."""
    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.transaction import TransactionContext

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    real = handle.raw

    subj = ox.NamedNode("https://cataforge.dev/instance/F-001")
    pred = ox.NamedNode("https://cataforge.dev/ontology/title")
    existing = ox.Quad(subj, pred, ox.Literal("before"))
    real.add(existing)

    class FlakyStore:
        def __init__(self, backing: object) -> None:
            self._backing = backing
            self._adds = 0

        def add(self, quad: object) -> None:
            self._adds += 1
            if self._adds == 1:  # the staged add fails
                raise RuntimeError("backend boom")
            self._backing.add(quad)  # restore re-adds succeed

        def remove(self, quad: object) -> None:
            self._backing.remove(quad)

    txn = TransactionContext(FlakyStore(real), config)
    txn.remove(existing)
    txn.add(ox.Quad(subj, pred, ox.Literal("after")))

    with pytest.raises(RuntimeError):
        txn.commit()

    assert any(q == existing for q in real), "removed quad must be restored on commit failure"


def test_restore_ghosts_surfaces_failures_instead_of_suppressing() -> None:
    """A failed ghost restore is reported, not silently swallowed."""
    from cataforge.domain.kg.repair import _restore_ghosts

    class FailingStore:
        def add(self, quad: object) -> None:
            raise RuntimeError("cannot restore")

    errors = _restore_ghosts(FailingStore(), {"F-001": ["q1", "q2"]}, ["r1"])
    assert errors, "restore failures must be surfaced, not suppressed"
    assert any("F-001" in e for e in errors)
