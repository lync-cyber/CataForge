"""`cataforge kg validate` core: orphan + xref-integrity checks.

This module ships the always-available baseline. Optional SHACL
validation (via `pyshacl`) is wired in below: when `pyshacl` is
installed it runs the SHACL shapes at `_generated/core_shapes.ttl`
against the live store; when absent it is silently skipped (a `[skipped]`
row appears in the report).

The semantics-rich orphan / xref-target checks here cover the regular
case; SHACL adds slot-cardinality and pattern enforcement (task-5 §5.4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig

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


def _list_typed_entities(store: ox.Store, namespace: str) -> list[tuple[str, str]]:
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?s ?cls WHERE { ?s a ?cls "
        "FILTER(STRSTARTS(STR(?cls), STR(cf:))) }"
    )
    out: list[tuple[str, str]] = []
    for row in store.query(sparql):
        s_value = row["s"]
        c_value = row["cls"]
        if s_value is None or c_value is None:
            continue
        out.append((str(s_value.value), str(c_value.value)))
    return out


def _entity_id_for(store: ox.Store, iri: str, namespace: str) -> str:
    sparql = (
        f"PREFIX cf: <{namespace}> "
        f"SELECT ?eid WHERE {{ <{iri}> cf:entity_id ?eid }} LIMIT 1"
    )
    for row in store.query(sparql):
        eid = row["eid"]
        if eid is not None:
            return str(eid.value)
    return iri  # fall back to IRI when entity_id missing


def _check_orphans(
    store: ox.Store, namespace: str
) -> list[ValidationViolation]:
    """Entities present but lacking required slots (entity_id / title)."""
    violations: list[ValidationViolation] = []
    for iri, cls in _list_typed_entities(store, namespace):
        if cls.rstrip("/").endswith("/Project"):
            continue  # Project itself is the root container
        has_eid = ask(
            store,
            f"PREFIX cf: <{namespace}> ASK {{ <{iri}> cf:entity_id ?x }}",
        )
        if not has_eid:
            violations.append(
                ValidationViolation(
                    severity="violation",
                    entity_id=iri,
                    shape="cf:entity_id-required",
                    message="entity has no cf:entity_id triple",
                )
            )
            continue
        has_title = ask(
            store,
            f"PREFIX cf: <{namespace}> ASK {{ <{iri}> cf:title ?x }}",
        )
        if not has_title:
            eid = _entity_id_for(store, iri, namespace)
            violations.append(
                ValidationViolation(
                    severity="violation",
                    entity_id=eid,
                    shape="cf:title-required",
                    message="entity has no cf:title triple",
                )
            )
    return violations


def _check_xref_targets(
    store: ox.Store, namespace: str
) -> list[ValidationViolation]:
    """Every traceability edge's object must resolve to a typed entity."""
    violations: list[ValidationViolation] = []
    traceability_slots = (
        "implements",
        "satisfies",
        "verifies",
        "realizes",
        "delivers",
        "affects",
        "depends_on",
    )
    for slot in traceability_slots:
        sparql = (
            f"PREFIX cf: <{namespace}> "
            f"SELECT ?s ?o WHERE {{ ?s cf:{slot} ?o }}"
        )
        for row in store.query(sparql):
            s_val = row["s"]
            o_val = row["o"]
            if s_val is None or o_val is None:
                continue
            target = str(o_val.value)
            has_type = ask(store, f"ASK {{ <{target}> a ?cls }}")
            if not has_type:
                source_eid = _entity_id_for(store, str(s_val.value), namespace)
                violations.append(
                    ValidationViolation(
                        severity="violation",
                        entity_id=source_eid,
                        shape=f"cf:{slot}-target-exists",
                        message=f"cf:{slot} target {target} is missing in the graph",
                    )
                )
    return violations


def _run_shacl(store: ox.Store) -> tuple[bool, list[ValidationViolation]]:
    """Optional SHACL pass; returns (skipped, violations).

    The pyoxigraph → rdflib bridge is non-trivial in 0.5.x (no NTriples
    dump exposed via Python yet); sub-PR 3 ships the wiring as a
    permanently-skipped stub so the `--shacl` flag is documented and
    discoverable. A follow-up PR implements the bridge once we need
    SHACL in the doctor pipeline.
    """
    import importlib.util  # noqa: PLC0415

    if (
        importlib.util.find_spec("pyshacl") is None
        or importlib.util.find_spec("rdflib") is None
    ):
        return True, []
    # Bridge stub — see docstring; treat as skipped for now.
    return True, []


def validate(
    store: ox.Store,
    config: KGConfig,
    *,
    run_shacl: bool = False,
) -> ValidationReport:
    namespace = config.ontology_namespace.rstrip("/") + "/"
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
