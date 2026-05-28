"""`cataforge kg validate` core: orphan + xref-integrity checks.

This module ships the always-available baseline. Optional SHACL
validation (via `pyshacl`) is wired in below: when `pyshacl` is
installed it runs the SHACL shapes at `_generated/core_shapes.ttl`
against the live store; when absent it is silently skipped (a `[skipped]`
row appears in the report).

The semantics-rich orphan / xref-target checks here cover the regular
case; SHACL adds slot-cardinality and pattern enforcement.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.kg._config import KGConfig
from cataforge.kg._sparql_utils import (
    _row_lookup,
    _strv,
    assert_safe_iri,
    cf_namespace,
)

if TYPE_CHECKING:
    import pyoxigraph as ox


@dataclass
class ValidationViolation:
    severity: str  # "violation" | "warning" | "info"
    entity_id: str
    shape: str
    message: str


@dataclass
class ValidationReport:
    violations: list[ValidationViolation] = field(default_factory=list)
    shacl_skipped: bool = False

    @property
    def ok(self) -> bool:
        return not any(v.severity == "violation" for v in self.violations)


def _check_orphans(store: ox.Store, namespace: str) -> list[ValidationViolation]:
    """Entities present but lacking required slots (entity_id / title).

    Single SELECT with OPTIONAL bindings, processed in Python, so the
    cost is one scan rather than O(N) ASKs.
    """
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?s ?cls ?eid ?title WHERE { "
        "  ?s a ?cls . "
        "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        f"  FILTER(?cls != <{namespace}Project>) "
        "  OPTIONAL { ?s cf:entity_id ?eid } "
        "  OPTIONAL { ?s cf:title     ?title } "
        "}"
    )
    violations: list[ValidationViolation] = []
    for row in store.query(sparql):
        s_iri = _strv(_row_lookup(row, "s"))
        if s_iri is None:
            continue
        eid = _strv(_row_lookup(row, "eid"))
        title = _strv(_row_lookup(row, "title"))
        if eid is None:
            violations.append(
                ValidationViolation(
                    severity="violation",
                    entity_id=s_iri,
                    shape="cf:entity_id-required",
                    message="entity has no cf:entity_id triple",
                )
            )
            continue
        if title is None:
            violations.append(
                ValidationViolation(
                    severity="violation",
                    entity_id=eid,
                    shape="cf:title-required",
                    message="entity has no cf:title triple",
                )
            )
    return violations


def _check_xref_targets(store: ox.Store, namespace: str) -> list[ValidationViolation]:
    """Every traceability edge's object must resolve to a typed entity.

    Single SELECT joins each traceability triple to its target's class
    (via OPTIONAL) and to the subject's entity_id so the result is
    self-contained — no per-row follow-up queries.
    """
    traceability_slots = (
        "implements",
        "satisfies",
        "verifies",
        "realizes",
        "delivers",
        "affects",
        "depends_on",
    )
    union_clauses = " UNION ".join(
        f'{{ ?s cf:{slot} ?o . BIND("{slot}" AS ?slot) }}' for slot in traceability_slots
    )
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?s ?s_eid ?slot ?o ?o_cls WHERE { "
        f"  {{ {union_clauses} }} "
        "  OPTIONAL { ?s cf:entity_id ?s_eid } "
        "  OPTIONAL { ?o a ?o_cls } "
        "}"
    )
    violations: list[ValidationViolation] = []
    for row in store.query(sparql):
        s_iri = _strv(_row_lookup(row, "s"))
        slot = _strv(_row_lookup(row, "slot"))
        target = _strv(_row_lookup(row, "o"))
        if s_iri is None or slot is None or target is None:
            continue
        if _row_lookup(row, "o_cls") is not None:
            continue
        source_eid = _strv(_row_lookup(row, "s_eid")) or s_iri
        with contextlib.suppress(ValueError):
            assert_safe_iri(target)
        violations.append(
            ValidationViolation(
                severity="violation",
                entity_id=source_eid,
                shape=f"cf:{slot}-target-exists",
                message=f"cf:{slot} target {target} is missing in the graph",
            )
        )
    return violations


def _pyoxigraph_to_rdflib(store: ox.Store):
    """Serialize all quads from pyoxigraph into an rdflib Graph."""
    import rdflib  # noqa: PLC0415

    g = rdflib.Graph()
    for quad in store.quads_for_pattern(None, None, None):
        s_term = quad.subject
        p_term = quad.predicate
        o_term = quad.object

        s = _ox_to_rdflib_term(s_term)
        p = _ox_to_rdflib_term(p_term)
        o = _ox_to_rdflib_term(o_term)
        if s is not None and p is not None and o is not None:
            g.add((s, p, o))
    return g


def _ox_to_rdflib_term(term):
    """Convert a pyoxigraph term to the equivalent rdflib term."""
    import pyoxigraph as oxi  # noqa: PLC0415
    import rdflib  # noqa: PLC0415

    if isinstance(term, oxi.NamedNode):
        return rdflib.URIRef(term.value)
    if isinstance(term, oxi.BlankNode):
        return rdflib.BNode(term.value)
    if isinstance(term, oxi.Literal):
        if term.language:
            return rdflib.Literal(term.value, lang=term.language)
        if term.datatype and term.datatype.value != "http://www.w3.org/2001/XMLSchema#string":
            return rdflib.Literal(term.value, datatype=rdflib.URIRef(term.datatype.value))
        # xsd:string is implicit in SPARQL 1.1; emit a plain literal so
        # the bridged rdflib graph matches the SHACL shapes' expectations.
        return rdflib.Literal(term.value)
    return None


def _find_shapes_file() -> Path | None:
    """Locate the SHACL shapes file from codegen output."""
    import importlib.resources  # noqa: PLC0415

    generated = Path(
        str(importlib.resources.files("cataforge.kg") / "_generated" / "core_shapes.ttl")
    )
    if generated.is_file():
        return generated
    return None


def _run_shacl(store: ox.Store) -> tuple[bool, list[ValidationViolation]]:
    """Optional SHACL pass; returns (skipped, violations).

    Bridges pyoxigraph store → rdflib Graph, then runs pyshacl
    validation against the generated SHACL shapes.
    """
    import importlib.util  # noqa: PLC0415

    if importlib.util.find_spec("pyshacl") is None or importlib.util.find_spec("rdflib") is None:
        return True, []

    shapes_path = _find_shapes_file()
    if shapes_path is None:
        return True, []

    import rdflib  # noqa: PLC0415
    from pyshacl import validate as shacl_validate  # noqa: PLC0415

    data_graph = _pyoxigraph_to_rdflib(store)
    shapes_graph = rdflib.Graph()
    shapes_graph.parse(str(shapes_path), format="turtle")

    conforms, results_graph, results_text = shacl_validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="none",
        abort_on_first=False,
    )

    violations: list[ValidationViolation] = []
    if not conforms:
        sh = rdflib.Namespace("http://www.w3.org/ns/shacl#")
        for result_node in results_graph.subjects(rdflib.RDF.type, sh.ValidationResult):
            focus = str(results_graph.value(result_node, sh.focusNode) or "")
            source_shape = str(results_graph.value(result_node, sh.sourceShape) or "")
            message = str(results_graph.value(result_node, sh.resultMessage) or "")
            severity_iri = str(results_graph.value(result_node, sh.resultSeverity) or "")
            if "Violation" in severity_iri:
                sev = "violation"
            elif "Warning" in severity_iri:
                sev = "warning"
            else:
                sev = "info"

            entity_id = focus.rsplit("/", 1)[-1] if "/" in focus else focus
            violations.append(
                ValidationViolation(
                    severity=sev,
                    entity_id=entity_id,
                    shape=source_shape.rsplit("/", 1)[-1] if "/" in source_shape else source_shape,
                    message=message or results_text[:200],
                )
            )

    return False, violations


def validate(
    store: ox.Store,
    config: KGConfig,
    *,
    run_shacl: bool = False,
) -> ValidationReport:
    namespace = cf_namespace(config)
    report = ValidationReport()
    report.violations.extend(_check_orphans(store, namespace))
    report.violations.extend(_check_xref_targets(store, namespace))
    if run_shacl:
        skipped, shacl_violations = _run_shacl(store)
        report.shacl_skipped = skipped
        report.violations.extend(shacl_violations)
    else:
        report.shacl_skipped = True
    return report
