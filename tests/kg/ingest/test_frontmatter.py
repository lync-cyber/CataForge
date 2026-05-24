"""Frontmatter relation keys → typed predicates."""

from __future__ import annotations

from cataforge.kg.ingest.frontmatter import (
    FRONTMATTER_PREDICATE_MAP,
    frontmatter_to_triples,
)


def _set(triples) -> set[tuple[str, str, object]]:
    return {(t.s, t.p, t.o) for t in triples}


def test_realizes_string_resolved_against_own_items() -> None:
    out = list(frontmatter_to_triples(
        "cfa:arch/M-001",
        {"realizes": "F-001"},
        own_item_iris={"F-001": "cfa:prd/F-001"},
    ))
    assert ("cfa:arch/M-001", "cfa:realizes", "cfa:prd/F-001") in _set(out)


def test_realizes_list_resolved() -> None:
    out = list(frontmatter_to_triples(
        "cfa:arch/M-001",
        {"realizes": ["F-001", "F-002"]},
        own_item_iris={
            "F-001": "cfa:prd/F-001",
            "F-002": "cfa:prd/F-002",
        },
    ))
    assert len(out) == 2


def test_deps_aliased_to_depends_on() -> None:
    out = list(frontmatter_to_triples(
        "cfk:doc/arch",
        {"deps": ["prd"]},
        known_item_iris={"prd": "cfk:doc/prd"},
    ))
    assert any(t.p == "cfa:dependsOn" for t in out)


def test_curie_value_passes_through() -> None:
    out = list(frontmatter_to_triples(
        "cfa:arch/M-001",
        {"implements": "cfa:other/M-002"},
    ))
    assert ("cfa:arch/M-001", "cfa:implements", "cfa:other/M-002") in _set(out)


def test_unresolved_id_dropped() -> None:
    out = list(frontmatter_to_triples(
        "cfa:arch/M-001",
        {"realizes": "F-999"},
        own_item_iris={"F-001": "cfa:prd/F-001"},
    ))
    assert out == []


def test_status_scalar_emitted() -> None:
    out = list(frontmatter_to_triples(
        "cfa:prd/F-001",
        {"status": "active", "priority": 1},
    ))
    triples = _set(out)
    assert ("cfa:prd/F-001", "cfa:status", "active") in triples
    assert ("cfa:prd/F-001", "cfa:priority", 1) in triples


def test_unknown_keys_silently_skipped() -> None:
    out = list(frontmatter_to_triples(
        "cfa:prd/F-001",
        {"unknown_field": "anything"},
    ))
    assert out == []


def test_all_design_relation_keys_present() -> None:
    # The eight V-model + cross-cut relations from the design JSON-LD must
    # all be in the map (regression guard against accidental deletions).
    for required in (
        "realizes", "implements", "decomposes", "validates",
        "conformsTo", "mitigates", "traces", "partOf",
    ):
        assert required in FRONTMATTER_PREDICATE_MAP
