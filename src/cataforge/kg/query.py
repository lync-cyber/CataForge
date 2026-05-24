"""High-level query helpers — SPARQL passthrough plus DSL/Cypher-lite/impact/coverage.

Wraps :class:`~cataforge.kg.store.GraphStore` so callers (CLI commands,
render templates, KG adapters) don't write raw SPARQL for the common
shapes. The four entry points are deliberately narrow:

* :func:`q`         — passthrough for hand-written SPARQL plus a JSON DSL
* :func:`cypher_lite` — single-pattern Cypher → SPARQL compiler
* :func:`impact`    — reverse ``cfa:dependsOn+`` traversal
* :func:`explain`   — does triple (s, p, o) exist, and if so why
* :func:`coverage`  — row × col matrix + GAP detection (RTM-style)

Anything fancier (multi-pattern Cypher, federated SPARQL, aggregations)
belongs in user-written SPARQL via :func:`q`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from cataforge.kg.ontology import NAMESPACES
from cataforge.kg.store import GraphStore


def _prefix_header(extra: Iterable[str] = ()) -> str:
    """Render the bundled CURIE prefixes as a SPARQL PREFIX header.

    Extra prefixes from L3 ontologies can be added by the caller via the
    ``extra`` iterable of ``"prefix: <iri>"`` strings."""
    lines = [f"PREFIX {p}: <{iri}>" for p, iri in NAMESPACES.items()]
    lines.extend(extra)
    return "\n".join(lines) + "\n"


def _expand_curie(token: str) -> str:
    """Expand ``prefix:local`` to full IRI; pass through if already absolute."""
    if token.startswith(("http://", "https://", "urn:")):
        return token
    if ":" not in token:
        raise ValueError(f"bare token without prefix or scheme: {token!r}")
    prefix, _, local = token.partition(":")
    base = NAMESPACES.get(prefix)
    if base is None:
        raise ValueError(
            f"unknown prefix {prefix!r} in {token!r}; register it in "
            "cataforge.kg.ontology before use.",
        )
    return base + local


# ---------- public dataclasses ----------

@dataclass
class CoverageMatrix:
    """Rectangular row × col coverage matrix plus GAP list.

    ``rows`` / ``cols`` are CURIE-shortened IRIs (or ``cfk:hasId`` values
    when the caller passes ``id_axis=True``); ``cells`` is a sparse dict
    keyed by ``(row, col)`` — absence means uncovered. ``gaps`` is the
    list of rows with zero coverage, in input order."""

    rows: list[str] = field(default_factory=list)
    cols: list[str] = field(default_factory=list)
    cells: dict[tuple[str, str], bool] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)

    @property
    def total_cells(self) -> int:
        return len(self.rows) * len(self.cols)

    @property
    def covered_cells(self) -> int:
        return sum(1 for v in self.cells.values() if v)

    @property
    def coverage_ratio(self) -> float:
        return self.covered_cells / self.total_cells if self.total_cells else 0.0


# ---------- coverage presets ----------

COVERAGE_PRESETS: dict[str, dict[str, str]] = {
    # Requirements Traceability Matrix: rows = Feature, cols = TestCase
    # validating it. Pattern: ?col cfa:validates ?row.
    "rtm":       {
        "rows": "cfa:Feature", "cols": "cfa:TestCase",
        "via": "cfa:validates", "direction": "col_to_row",
    },
    # Test → Implementation coverage: rows = TestCase, cols = CodeUnit it
    # exercises (via the validated Module the CU implements).
    "test":      {
        "rows": "cfa:Module", "cols": "cfa:TestCase",
        "via": "cfa:validates", "direction": "col_to_row",
    },
    # Risk mitigation matrix: rows = Risk, cols = CodeUnit that mitigates it.
    # Pattern: ?col cfa:mitigates ?row.
    "risk":      {
        "rows": "cfa:Risk", "cols": "cfa:CodeUnit",
        "via": "cfa:mitigates", "direction": "col_to_row",
    },
    # Interface conformance: rows = Module, cols = Interface its CodeUnits
    # conform to. Forward direction.
    "interface": {
        "rows": "cfa:Interface", "cols": "cfa:CodeUnit",
        "via": "cfa:conformsTo", "direction": "col_to_row",
    },
}


# ---------- q (SPARQL + DSL) ----------

def q(
    store: GraphStore,
    *,
    sparql: str | None = None,
    dsl: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Unified query entry — either a SPARQL string or a JSON DSL.

    Exactly one of ``sparql`` / ``dsl`` must be set. The DSL shape:

    ``{"rel": "<curie>", "src_type": "<curie>", "dst_type": "<curie>",
       "src": "<iri>", "dst": "<iri>"}``

    All four shape fields are optional; supplied fields tighten the
    pattern, omitted fields stay unbound. The compiled SPARQL is a
    plain ``SELECT ?src ?dst`` with PREFIX header — callers that want
    different projection lists should use ``sparql=`` directly."""
    if (sparql is None) == (dsl is None):
        raise ValueError("pass exactly one of sparql= or dsl=")
    if sparql is not None:
        return store.query(_prefix_header() + sparql)
    assert dsl is not None
    return store.query(_dsl_to_sparql(dsl))


def _dsl_to_sparql(dsl: dict[str, Any]) -> str:
    rel = dsl.get("rel")
    src_type = dsl.get("src_type")
    dst_type = dsl.get("dst_type")
    src = dsl.get("src")
    dst = dsl.get("dst")

    if not rel:
        raise ValueError("DSL requires 'rel' (the predicate curie)")

    parts = [_prefix_header(), "SELECT DISTINCT ?src ?dst WHERE {"]
    if src_type:
        parts.append(f"  ?src a {src_type} .")
    if dst_type:
        parts.append(f"  ?dst a {dst_type} .")
    parts.append(f"  ?src {rel} ?dst .")
    if src:
        parts.append(f"  FILTER (?src = <{_expand_curie(src)}>)")
    if dst:
        parts.append(f"  FILTER (?dst = <{_expand_curie(dst)}>)")
    parts.append("} ORDER BY ?src ?dst")
    return "\n".join(parts)


# ---------- cypher_lite ----------

_CYPHER_MATCH_RE = re.compile(
    r"""^
    \s*MATCH\s*
    \(\s*(?P<a_var>\w+)\s*:\s*(?P<a_type>[\w:]+)\s*\)
    \s*-\s*\[\s*:\s*(?P<rel>[\w:]+)\s*\]\s*->\s*
    \(\s*(?P<b_var>\w+)\s*:\s*(?P<b_type>[\w:]+)\s*\)
    \s*RETURN\s+(?P<ret>[\w,\s]+)
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)


def cypher_lite(store: GraphStore, expr: str) -> list[dict[str, str]]:
    """Compile a single-pattern Cypher MATCH...RETURN into SPARQL and run.

    Supported shape::

        MATCH (a:Module)-[:implements]->(b:Feature) RETURN a, b

    Multi-pattern paths, WHERE clauses, aggregations, and write
    operations (CREATE/MERGE/DELETE) are deliberately out of scope —
    callers needing those should write SPARQL via :func:`q`."""
    m = _CYPHER_MATCH_RE.match(expr.strip())
    if m is None:
        raise ValueError(
            "cypher_lite only supports single-pattern MATCH ... RETURN; "
            "use q(sparql=...) for anything more complex.",
        )
    a_var = m.group("a_var")
    b_var = m.group("b_var")
    a_type = _ensure_curie(m.group("a_type"))
    b_type = _ensure_curie(m.group("b_type"))
    rel = _ensure_curie(m.group("rel"))
    ret_vars = [v.strip() for v in m.group("ret").split(",") if v.strip()]

    select_clause = " ".join(f"?{v}" for v in ret_vars)
    sparql = (
        _prefix_header()
        + f"SELECT DISTINCT {select_clause} WHERE {{\n"
        + f"  ?{a_var} a {a_type} .\n"
        + f"  ?{b_var} a {b_type} .\n"
        + f"  ?{a_var} {rel} ?{b_var} .\n"
        + f"}} ORDER BY {select_clause}\n"
    )
    return store.query(sparql)


def _ensure_curie(token: str) -> str:
    """Add a default ``cfa:`` prefix to a bare type/relation token."""
    return token if ":" in token else f"cfa:{token}"


# ---------- impact ----------

def impact(
    store: GraphStore,
    node: str,
    *,
    max_depth: int = 5,
) -> list[str]:
    """Return CURIE-shortened IRIs of nodes that transitively depend on ``node``.

    Uses the ``cfa:dependsOn+`` SPARQL property path. ``max_depth`` is
    advisory only — rdflib's ``+`` operator already terminates on
    fixed-point — but it's threaded through for future plugin backends
    (e.g. oxigraph) that may bound traversal explicitly."""
    del max_depth  # advisory; rdflib's + handles termination
    full_iri = _expand_curie(node)
    sparql = (
        _prefix_header()
        + "SELECT DISTINCT ?dep WHERE {\n"
        + f"  ?dep cfa:dependsOn+ <{full_iri}> .\n"
        + "} ORDER BY ?dep\n"
    )
    rows = store.query(sparql)
    return [_shorten_iri(r["dep"]) for r in rows]


# ---------- explain ----------

@dataclass(frozen=True)
class ExplainResult:
    """Why does triple (s, p, o) exist (or not)?

    ``derivation`` is one of:
      * ``"base"``       — present as a direct assertion
      * ``"inverse"``    — present because (o, inverse_of_p, s) is asserted
      * ``"transitive"`` — present via a multi-step path of the same predicate
      * ``"absent"``     — no derivation found
    ``path`` carries the intermediate IRIs when ``derivation=transitive``."""

    derivation: str
    path: list[str] = field(default_factory=list)


def explain(
    store: GraphStore,
    src: str,
    predicate: str,
    dst: str,
) -> ExplainResult:
    """Diagnose why a triple exists in the store (after reasoning)."""
    src_iri = _expand_curie(src)
    dst_iri = _expand_curie(dst)
    pred_iri = _expand_curie(predicate)

    direct_rows = store.query(
        f"ASK {{ <{src_iri}> <{pred_iri}> <{dst_iri}> }}",
    )
    if not direct_rows or direct_rows[0]["_ask"] != "true":
        return ExplainResult(derivation="absent")

    # Is there an inverseOf that explains it?
    inverse_rows = store.query(
        _prefix_header()
        + "SELECT ?inv WHERE {\n"
        + f"  <{pred_iri}> owl:inverseOf ?inv .\n"
        + f"  <{dst_iri}> ?inv <{src_iri}> .\n"
        + "}",
    )
    if inverse_rows:
        return ExplainResult(derivation="inverse")

    # Multi-hop check: same predicate chained?
    hop_rows = store.query(
        _prefix_header()
        + "SELECT ?mid WHERE {\n"
        + f"  <{src_iri}> <{pred_iri}> ?mid .\n"
        + f"  ?mid <{pred_iri}>+ <{dst_iri}> .\n"
        + "  FILTER (?mid != <" + dst_iri + ">)\n"
        + "} LIMIT 1",
    )
    if hop_rows:
        return ExplainResult(
            derivation="transitive",
            path=[src, _shorten_iri(hop_rows[0]["mid"]), dst],
        )

    return ExplainResult(derivation="base")


# ---------- coverage ----------

def coverage(
    store: GraphStore,
    *,
    rows_class: str,
    cols_class: str,
    via: str,
    direction: str = "col_to_row",
    preset: str | None = None,
) -> CoverageMatrix:
    """Build a row × col coverage matrix between two classes via a predicate.

    Parameters
    ----------
    rows_class, cols_class :
        CURIEs for ``a/owl:Class`` membership tests, e.g. ``cfa:Feature``.
    via :
        Predicate CURIE wiring rows to cols.
    direction :
        ``"col_to_row"`` (default; matches ``?col <via> ?row`` — the
        natural RTM phrasing where TestCase --validates--> Feature) or
        ``"row_to_col"`` (forward, ``?row <via> ?col``).
    preset :
        Optional :data:`COVERAGE_PRESETS` key — when set, *all* other
        kwargs are overridden. Convenience shortcut for the four common
        matrices.
    """
    if preset is not None:
        if preset not in COVERAGE_PRESETS:
            raise ValueError(
                f"unknown coverage preset {preset!r}; "
                f"choose from {sorted(COVERAGE_PRESETS)}",
            )
        cfg = COVERAGE_PRESETS[preset]
        rows_class = cfg["rows"]
        cols_class = cfg["cols"]
        via = cfg["via"]
        direction = cfg["direction"]

    rows_iris = [
        r["x"] for r in store.query(
            _prefix_header()
            + f"SELECT ?x WHERE {{ ?x a {rows_class} }} ORDER BY ?x",
        )
    ]
    cols_iris = [
        r["x"] for r in store.query(
            _prefix_header()
            + f"SELECT ?x WHERE {{ ?x a {cols_class} }} ORDER BY ?x",
        )
    ]

    if direction == "col_to_row":
        pattern = f"?col {via} ?row"
    elif direction == "row_to_col":
        pattern = f"?row {via} ?col"
    else:
        raise ValueError(f"unknown direction {direction!r}")

    pair_rows = store.query(
        _prefix_header()
        + "SELECT ?row ?col WHERE {\n"
        + f"  ?row a {rows_class} .\n"
        + f"  ?col a {cols_class} .\n"
        + f"  {pattern} .\n"
        + "} ORDER BY ?row ?col",
    )
    cells: dict[tuple[str, str], bool] = {
        (_shorten_iri(r["row"]), _shorten_iri(r["col"])): True
        for r in pair_rows
    }
    rows_short = [_shorten_iri(r) for r in rows_iris]
    cols_short = [_shorten_iri(c) for c in cols_iris]
    gaps = [r for r in rows_short if not any(
        (r, c) in cells for c in cols_short
    )]
    return CoverageMatrix(
        rows=rows_short, cols=cols_short, cells=cells, gaps=gaps,
    )


# ---------- helpers ----------

def _shorten_iri(iri: str) -> str:
    """Inverse of :func:`_expand_curie` — produce ``prefix:local`` when possible."""
    for prefix, base in NAMESPACES.items():
        if iri.startswith(base):
            return f"{prefix}:{iri[len(base):]}"
    return iri
