"""3-way merge between KG / file / render — adds, removals, conflicts, apply."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from cataforge.kg.delta import (
    FUNCTIONAL_PREDICATES,
    Conflict,
    DeltaReport,
    apply,
    compute_delta,
)
from cataforge.kg.store import RDFLibStore, Triple


def _t(s: str, p: str, o) -> Triple:
    return Triple(s=s, p=p, o=o)


def _set(triples: Iterable[Triple]) -> set[Triple]:
    return set(triples)


def test_clean_when_kg_and_file_identical() -> None:
    triples = [_t("cfa:prd/F-001", "rdf:type", "cfa:Feature")]
    rep = compute_delta(triples, triples)
    assert rep.is_clean


def test_addition_when_file_has_new_triple() -> None:
    kg = [_t("cfa:prd/F-001", "rdf:type", "cfa:Feature")]
    src = kg + [_t("cfa:prd/F-001", "rdfs:label", "login")]
    rep = compute_delta(kg, src)
    assert rep.additions == [_t("cfa:prd/F-001", "rdfs:label", "login")]
    assert rep.removals == []


def test_removal_when_file_drops_triple() -> None:
    kg = [
        _t("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        _t("cfa:prd/F-001", "rdfs:label", "login"),
    ]
    src = [_t("cfa:prd/F-001", "rdf:type", "cfa:Feature")]
    rep = compute_delta(kg, src)
    assert rep.removals == [_t("cfa:prd/F-001", "rdfs:label", "login")]


def test_functional_predicate_disagreement_is_conflict() -> None:
    kg = [_t("cfa:prd/F-001", "cfa:status", "active")]
    src = [_t("cfa:prd/F-001", "cfa:status", "deprecated")]
    rep = compute_delta(kg, src)
    assert rep.conflicts and rep.conflicts[0].predicate == "cfa:status"
    # The disagreement does not also leak into adds/removals.
    assert rep.additions == []
    assert rep.removals == []


def test_non_functional_predicate_difference_is_delta_not_conflict() -> None:
    # cfa:implements is multi-valued — different values just means the
    # relation set changed, no conflict.
    kg = [_t("cfa:cu/CU-1", "cfa:implements", "cfa:arch/M-1")]
    src = [_t("cfa:cu/CU-1", "cfa:implements", "cfa:arch/M-2")]
    rep = compute_delta(kg, src)
    assert rep.conflicts == []
    assert _t("cfa:cu/CU-1", "cfa:implements", "cfa:arch/M-2") in rep.additions
    assert _t("cfa:cu/CU-1", "cfa:implements", "cfa:arch/M-1") in rep.removals


def test_subject_scope_filters_out_unrelated_triples() -> None:
    kg = [
        _t("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        _t("cfa:other/F-099", "rdf:type", "cfa:Feature"),  # outside scope
    ]
    src = [_t("cfa:prd/F-001", "rdf:type", "cfa:Feature")]
    rep = compute_delta(
        kg, src, subject_scope={"cfa:prd/F-001"},
    )
    # F-099 must NOT show up as a removal.
    assert rep.is_clean


def test_three_way_only_file_moved_no_conflict() -> None:
    # render shows what KG and file used to agree on; file moved; KG stayed.
    # → no conflict, file value flows in as add/remove naturally.
    render = [_t("cfa:prd/F-001", "cfa:status", "proposed")]
    kg = [_t("cfa:prd/F-001", "cfa:status", "proposed")]
    src = [_t("cfa:prd/F-001", "cfa:status", "active")]
    rep = compute_delta(kg, src, render_triples=render)
    assert rep.conflicts == []
    assert _t("cfa:prd/F-001", "cfa:status", "active") in rep.additions
    assert _t("cfa:prd/F-001", "cfa:status", "proposed") in rep.removals


def test_three_way_only_kg_moved_kg_wins_silently() -> None:
    # render = file = old value; kg moved on its own (via update-entity).
    # → kg's value stays; file is treated as stale, no conflict surfaced.
    render = [_t("cfa:prd/F-001", "cfa:status", "proposed")]
    kg = [_t("cfa:prd/F-001", "cfa:status", "active")]
    src = [_t("cfa:prd/F-001", "cfa:status", "proposed")]
    rep = compute_delta(kg, src, render_triples=render)
    assert rep.conflicts == []
    # file's stale "proposed" is suppressed; nothing applies.
    assert not any(t.p == "cfa:status" for t in rep.additions)
    assert not any(t.p == "cfa:status" for t in rep.removals)


def test_three_way_both_sides_moved_real_conflict() -> None:
    render = [_t("cfa:prd/F-001", "cfa:status", "proposed")]
    kg = [_t("cfa:prd/F-001", "cfa:status", "active")]
    src = [_t("cfa:prd/F-001", "cfa:status", "deprecated")]
    rep = compute_delta(kg, src, render_triples=render)
    assert len(rep.conflicts) == 1
    c = rep.conflicts[0]
    assert (c.kg_value, c.file_value, c.render_value) == (
        "active", "deprecated", "proposed",
    )


def test_apply_kg_wins_skips_conflicts(tmp_path) -> None:
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([_t("cfa:prd/F-001", "cfa:status", "active")])

    report = DeltaReport(
        additions=[_t("cfa:prd/F-001", "rdfs:label", "login")],
        conflicts=[
            Conflict(
                subject="cfa:prd/F-001", predicate="cfa:status",
                kg_value="active", file_value="deprecated",
                render_value=None,
            ),
        ],
    )
    added = apply(report, store, strategy="kg-wins")
    assert added == 1
    rows = store.query(
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "SELECT ?o WHERE { <https://cataforge.dev/ontology/artifact#prd/F-001>"
        " cfa:status ?o }",
    )
    # Status unchanged — file value lost (kg-wins) but no exception either.
    assert rows == [{"o": "active"}]


def test_apply_file_wins_overwrites_conflict(tmp_path) -> None:
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([_t("cfa:prd/F-001", "cfa:status", "active")])

    report = DeltaReport(
        conflicts=[
            Conflict(
                subject="cfa:prd/F-001", predicate="cfa:status",
                kg_value="active", file_value="deprecated",
                render_value=None,
            ),
        ],
    )
    apply(report, store, strategy="file-wins")
    rows = store.query(
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "SELECT ?o WHERE { <https://cataforge.dev/ontology/artifact#prd/F-001>"
        " cfa:status ?o }",
    )
    assert rows == [{"o": "deprecated"}]


def test_apply_prompt_is_noop(tmp_path) -> None:
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([_t("cfa:prd/F-001", "cfa:status", "active")])

    report = DeltaReport(
        additions=[_t("cfa:prd/F-001", "rdfs:label", "login")],
        conflicts=[
            Conflict(
                subject="cfa:prd/F-001", predicate="cfa:status",
                kg_value="active", file_value="deprecated",
                render_value=None,
            ),
        ],
    )
    added = apply(report, store, strategy="prompt")
    assert added == 0
    assert len(store) == 1  # neither the conflict nor the addition applied


def test_apply_rejects_unknown_strategy(tmp_path) -> None:
    store = RDFLibStore()
    store.load(tmp_path)
    with pytest.raises(ValueError, match="unknown strategy"):
        apply(DeltaReport(), store, strategy="bogus")


def test_format_renders_counts_and_conflict_detail() -> None:
    report = DeltaReport(
        additions=[_t("cfa:x", "rdf:type", "cfa:Feature")],
        removals=[],
        conflicts=[
            Conflict(
                subject="cfa:x", predicate="cfa:status",
                kg_value="active", file_value="deprecated",
                render_value="proposed",
            ),
        ],
    )
    text = report.format()
    assert "+adds      : 1" in text
    assert "!conflicts : 1" in text
    assert "render=" in text


def test_idempotent_apply(tmp_path) -> None:
    store = RDFLibStore()
    store.load(tmp_path)
    src = [
        _t("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        _t("cfa:prd/F-001", "rdfs:label", "login"),
    ]
    rep_first = compute_delta(list(store), src)
    apply(rep_first, store, strategy="file-wins")
    rep_second = compute_delta(list(_iter_subj_pred_obj(store)), src)
    assert rep_second.is_clean


def test_functional_predicates_set_is_documented() -> None:
    # Sanity check that we shipped the predicates the design note calls
    # functional. Add new ones here and in delta.py when ontology grows.
    for pred in ("cfk:hasId", "cfa:status", "cfa:priority", "cfa:codeUnitKind"):
        assert pred in FUNCTIONAL_PREDICATES


def _iter_subj_pred_obj(store: RDFLibStore) -> list[Triple]:
    """Re-derive Triple from the store's expanded-IRI quad iterator."""
    out: list[Triple] = []
    for s, p, o, _g in store:
        out.append(_iri_to_curie(s, p, o))
    return out


_PREFIX_MAP = {
    "https://cataforge.dev/ontology/kernel#":   "cfk:",
    "https://cataforge.dev/ontology/process#":  "cfp:",
    "https://cataforge.dev/ontology/artifact#": "cfa:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://www.w3.org/2000/01/rdf-schema#":       "rdfs:",
}


def _shorten(iri: str) -> str:
    for prefix, short in _PREFIX_MAP.items():
        if iri.startswith(prefix):
            return short + iri[len(prefix):]
    return iri


def _iri_to_curie(s: str, p: str, o: str) -> Triple:
    return Triple(s=_shorten(s), p=_shorten(p), o=_shorten(o))
