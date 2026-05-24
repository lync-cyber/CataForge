"""3-way merge between the KG, the source Markdown, and the last render.

Used by the PostToolUse auto-ingest path (design §3.x) and by the
``cataforge kg ingest`` CLI to fold file-side edits back into the graph
without overwriting independent graph mutations.

Three input "worlds":

* **kg**     — what currently lives in ``.doc-graph/instances.nq``
* **file**   — what re-ingesting the source Markdown *now* would produce
* **render** — what the last KG → Markdown render produced (optional;
  acts as the common ancestor that lets us distinguish "user edited the
  file" from "user ran ``cataforge kg update-entity`` directly")

Conflicts are restricted to **functional predicates** (single-valued by
ontology contract — ``cfk:hasId``, ``cfk:contentHash``, ``cfa:status``,
``cfa:priority``, ``cfa:codeUnitKind``). Multi-valued relations
(``cfa:implements``, ``cfa:references``, etc.) just produce adds and
removals — the union/diff is the merge result by definition.

Without a render snapshot the merge collapses to 2-way: anything in
``file`` but not ``kg`` is an add; anything in ``kg`` but not ``file``
is a removal; functional-predicate disagreements are conflicts.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from cataforge.kg.store import GraphStore, Triple

FUNCTIONAL_PREDICATES: frozenset[str] = frozenset({
    "cfk:hasId",
    "cfk:contentHash",
    "rdfs:label",
    "cfa:status",
    "cfa:priority",
    "cfa:codeUnitKind",
    "dct:type",
})


@dataclass(frozen=True)
class Conflict:
    """A single functional-predicate disagreement between the three sides.

    ``render_value`` is None when no render snapshot was supplied (the
    2-way fallback). In 3-way mode it carries the value that was there
    when the two sides last agreed."""

    subject: str
    predicate: str
    kg_value: str | int | float | bool | None
    file_value: str | int | float | bool | None
    render_value: str | int | float | bool | None


@dataclass
class DeltaReport:
    """Outcome of :func:`compute_delta`.

    ``additions`` and ``removals`` are net edits the caller can safely
    apply without ambiguity. ``conflicts`` need a strategy choice."""

    additions: list[Triple] = field(default_factory=list)
    removals: list[Triple] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when nothing changed — caller may skip the apply step."""
        return not self.additions and not self.removals and not self.conflicts

    def format(self) -> str:
        """Render a short human-readable summary."""
        lines = [
            f"+adds      : {len(self.additions)}",
            f"-removes   : {len(self.removals)}",
            f"!conflicts : {len(self.conflicts)}",
        ]
        if self.conflicts:
            lines.append("")
            lines.append("conflicts (functional-predicate disagreements):")
            for c in self.conflicts:
                lines.append(
                    f"  {c.subject} {c.predicate} → "
                    f"kg={c.kg_value!r} file={c.file_value!r}"
                    + (f" render={c.render_value!r}" if c.render_value is not None else ""),
                )
        return "\n".join(lines)


def _filter_by_scope(
    triples: Iterable[Triple], scope: set[str] | None,
) -> set[Triple]:
    if scope is None:
        return set(triples)
    return {t for t in triples if t.s in scope}


def _index_functional(
    triples: set[Triple],
) -> dict[tuple[str, str], str | int | float | bool]:
    """Pick the (s, p) → o map for functional predicates.

    If a side accidentally has more than one value for a functional
    (s, p) — e.g. malformed ingest — we keep the lexicographically first
    by ``str(o)`` so the conflict comparison is deterministic."""
    out: dict[tuple[str, str], str | int | float | bool] = {}
    for t in triples:
        if t.p not in FUNCTIONAL_PREDICATES:
            continue
        key = (t.s, t.p)
        if key in out and str(out[key]) <= str(t.o):
            continue
        out[key] = t.o
    return out


def compute_delta(
    kg_triples: Iterable[Triple],
    file_triples: Iterable[Triple],
    *,
    subject_scope: set[str] | None = None,
    render_triples: Iterable[Triple] | None = None,
) -> DeltaReport:
    """Compute additions / removals / conflicts between the three worlds.

    ``subject_scope`` restricts the comparison to triples whose subject
    is in the set — typical use is ``{doc_iri} ∪ {item.iri for item in result.items}``
    so re-ingesting one document doesn't propose removing triples from
    every other document."""
    kg = _filter_by_scope(kg_triples, subject_scope)
    src = _filter_by_scope(file_triples, subject_scope)
    render = (
        _filter_by_scope(render_triples, subject_scope)
        if render_triples is not None
        else None
    )

    kg_idx = _index_functional(kg)
    src_idx = _index_functional(src)
    render_idx = _index_functional(render) if render is not None else {}

    conflicts: list[Conflict] = []
    suppressed_keys: set[tuple[str, str]] = set()
    for key in kg_idx.keys() & src_idx.keys():
        kg_val = kg_idx[key]
        src_val = src_idx[key]
        if kg_val == src_val:
            continue
        ancestor = render_idx.get(key) if render is not None else None
        # 3-way: if only one side moved off the ancestor, the other side
        # is authoritative — no conflict, fold into adds/removals naturally.
        if render is not None:
            if ancestor == kg_val:
                # file moved, kg stayed — let the normal diff carry it.
                continue
            if ancestor == src_val:
                # kg moved, file stayed — keep kg, drop file's value.
                suppressed_keys.add(key)
                continue
        s, p = key
        conflicts.append(
            Conflict(
                subject=s, predicate=p,
                kg_value=kg_val, file_value=src_val,
                render_value=ancestor,
            ),
        )
        suppressed_keys.add(key)

    additions = sorted(
        (
            t for t in src - kg
            if (t.s, t.p) not in suppressed_keys
        ),
        key=lambda t: (t.s, t.p, str(t.o)),
    )
    removals = sorted(
        (
            t for t in kg - src
            if (t.s, t.p) not in suppressed_keys
        ),
        key=lambda t: (t.s, t.p, str(t.o)),
    )
    return DeltaReport(
        additions=additions,
        removals=removals,
        conflicts=conflicts,
    )


def apply(
    report: DeltaReport,
    store: GraphStore,
    *,
    strategy: str = "kg-wins",
) -> int:
    """Apply the delta to a store under the chosen conflict strategy.

    Strategies
    ----------
    ``kg-wins``  : ignore conflicts entirely; apply only the no-conflict
                   adds and removals.
    ``file-wins``: for each conflict, remove the KG value and add the
                   file value, then apply the rest of the delta.
    ``prompt``   : apply nothing — caller is expected to surface the
                   conflicts to a human (or write them to a conflicts/
                   directory per design §3.x) and call ``apply`` again
                   later with a resolved report.

    Returns the number of triples added — useful for "anything changed?"
    bookkeeping in PostToolUse hooks."""
    if strategy not in {"kg-wins", "file-wins", "prompt"}:
        raise ValueError(f"unknown strategy {strategy!r}")

    if strategy == "prompt":
        return 0

    if strategy == "file-wins":
        for c in report.conflicts:
            if c.kg_value is not None:
                store.remove(Triple(s=c.subject, p=c.predicate, o=c.kg_value))
            if c.file_value is not None:
                store.add([Triple(s=c.subject, p=c.predicate, o=c.file_value)])

    for t in report.removals:
        store.remove(t)
    if report.additions:
        store.add(report.additions)
    return len(report.additions)
