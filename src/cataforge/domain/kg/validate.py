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
from typing import TYPE_CHECKING, Any

from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    assert_safe_iri,
    cf_namespace,
    select_rows,
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
    # Project + the structural container classes (Document / Section) are
    # identified by their `id` IRI, not by a `cf:entity_id` literal, so they
    # are exempt from the entity_id-required shape.
    id_identified = ", ".join(f"<{namespace}{cls}>" for cls in ("Project", "Document", "Section"))
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?s ?cls ?eid ?title WHERE { "
        "  ?s a ?cls . "
        "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        f"  FILTER(?cls NOT IN ({id_identified})) "
        "  OPTIONAL { ?s cf:entity_id ?eid } "
        "  OPTIONAL { ?s cf:title     ?title } "
        "}"
    )
    violations: list[ValidationViolation] = []
    for row in select_rows(store, sparql):
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
    for row in select_rows(store, sparql):
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


def _pyoxigraph_to_rdflib(store: ox.Store) -> Any:
    """Bridge the store's default graph into an rdflib Graph.

    pyoxigraph serializes to N-Triples and rdflib parses it back; both are
    spec-compliant, so datatypes, language tags and IRI/blank-node escaping
    round-trip without a hand-maintained term mapping. All CataForge data
    lives in the default graph (see _quads.py — every Quad is built without a
    graph name), which is also the only graph the SHACL shapes target.
    """
    import pyoxigraph as ox  # noqa: PLC0415
    import rdflib  # noqa: PLC0415

    nt = store.dump(None, ox.RdfFormat.N_TRIPLES, from_graph=ox.DefaultGraph())
    graph = rdflib.Graph()
    graph.parse(data=nt, format="nt")
    return graph


def _find_shapes_file() -> Path | None:
    """Locate the SHACL shapes file from codegen output."""
    import importlib.resources  # noqa: PLC0415

    generated = Path(
        str(importlib.resources.files("cataforge.domain.kg") / "_generated" / "core_shapes.ttl")
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
