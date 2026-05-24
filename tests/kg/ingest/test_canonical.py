"""Triple canonicalisation — dedup, whitespace, deterministic sort."""

from __future__ import annotations

from cataforge.kg.ingest.canonical import canonicalize
from cataforge.kg.store import Triple


def test_dedup_identical_triples() -> None:
    out = canonicalize([
        Triple("cfa:F-001", "rdfs:label", "login"),
        Triple("cfa:F-001", "rdfs:label", "login"),
    ])
    assert len(out) == 1


def test_whitespace_normalised_in_string_literals() -> None:
    out = canonicalize([
        Triple("cfa:F-001", "rdfs:label", "  login  "),
        Triple("cfa:F-001", "rdfs:label", "login"),
        Triple("cfa:F-001", "rdfs:label", "log\n in"),
    ])
    # The first two collapse together; the third collapses internal whitespace.
    assert Triple("cfa:F-001", "rdfs:label", "login") in out
    assert Triple("cfa:F-001", "rdfs:label", "log in") in out
    assert len(out) == 2


def test_sort_is_deterministic() -> None:
    a = canonicalize([
        Triple("cfa:F-002", "rdf:type", "cfa:Feature"),
        Triple("cfa:F-001", "rdf:type", "cfa:Feature"),
    ])
    b = canonicalize([
        Triple("cfa:F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:F-002", "rdf:type", "cfa:Feature"),
    ])
    assert a == b
    assert a[0].s < a[1].s


def test_non_string_object_passes_through() -> None:
    out = canonicalize([
        Triple("cfa:F-001", "cfa:priority", 1),
        Triple("cfa:F-002", "cfa:flag", True),
    ])
    pri = next(t for t in out if t.s == "cfa:F-001")
    flag = next(t for t in out if t.s == "cfa:F-002")
    assert pri.o == 1
    assert flag.o is True


def test_idempotent_on_repeat_application() -> None:
    seed = [Triple("cfa:F-001", "rdfs:label", "  login\n\n  ")]
    once = canonicalize(seed)
    twice = canonicalize(once)
    assert once == twice
