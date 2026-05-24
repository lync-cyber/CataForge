"""Performance-budget benchmark harness.

Runs five canonical operations against synthetic fixtures, compares each
against the budget declared in ``.cataforge/kg/perf-budget.json``, and
emits a report. Per design note §8, threshold breaches trigger a WARN
suggesting an oxigraph backend swap rather than a hard FAIL — CI hosts
vary enough that a strict gate would flap.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdflib import Literal, URIRef

from cataforge.kg.ontology import load_ontology, load_shapes
from cataforge.kg.reasoning import infer
from cataforge.kg.store import RDFLibStore, Triple

DEFAULT_BUDGET: dict[str, Any] = {
    "full_rebuild": {"max_ms": 2000, "docs": 100},
    "incremental_update": {"max_ms": 200},
    "shacl_validate": {"max_ms": 1000, "triples": 5000},
    "owl_rl_infer": {"max_ms": 1500, "triples": 5000},
    "single_sparql_query": {"max_ms": 50},
    "oxigraph_autoswap_threshold_triples": 5000,
}

# Conservative iteration count for sparql micro-benchmark so the timing
# averages out clock jitter without bloating wall-clock cost.
_QUERY_REPEAT = 25

CFA = "https://cataforge.dev/ontology/artifact#"
CFK = "https://cataforge.dev/ontology/kernel#"


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    elapsed_ms: float
    budget_ms: float | None
    detail: str

    @property
    def status(self) -> str:
        if self.budget_ms is None:
            return "INFO"
        return "OK" if self.elapsed_ms <= self.budget_ms else "WARN"


def load_budget(path: str | Path | None) -> dict[str, Any]:
    """Load ``perf-budget.json`` or return the in-memory defaults."""
    if path is None:
        return DEFAULT_BUDGET
    p = Path(path)
    if not p.is_file():
        return DEFAULT_BUDGET
    return dict(json.loads(p.read_text(encoding="utf-8")))


def synth_triples(n: int) -> Iterator[Triple]:
    """Yield ``n`` triples covering Feature / Module / implements edges.

    Layout: every 4th triple closes an implements edge so the graph stays
    realistic (mix of type assertions, labels, attributes, and relations)
    rather than a single rdf:type firehose."""
    for i in range(n):
        kind = i % 4
        if kind == 0:
            yield Triple(f"cfa:F-{i:06d}", "rdf:type", "cfa:Feature")
        elif kind == 1:
            yield Triple(f"cfa:F-{i - 1:06d}", "rdfs:label", f"feature-{i - 1}")
        elif kind == 2:
            yield Triple(f"cfa:M-{i:06d}", "rdf:type", "cfa:Module")
        else:
            yield Triple(
                f"cfa:M-{i - 1:06d}", "cfa:implements", f"cfa:F-{i - 3:06d}",
            )


def _populate(store: RDFLibStore, n: int) -> None:
    # Batch via list to avoid one-add-per-triple Python overhead skewing
    # the timing toward dict-lookup costs.
    store.add(list(synth_triples(n)))


def benchmark_full_rebuild(project_root: Path, docs: int) -> BenchmarkResult:
    triples = docs * 50  # rough proxy: 50 triples per doc
    store = RDFLibStore()
    store.load(project_root)
    t0 = time.perf_counter()
    _populate(store, triples)
    store.persist()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return BenchmarkResult(
        name="full_rebuild",
        elapsed_ms=elapsed_ms,
        budget_ms=None,
        detail=f"{docs} docs ≈ {triples} triples",
    )


def benchmark_incremental_update(project_root: Path) -> BenchmarkResult:
    store = RDFLibStore()
    store.load(project_root)
    _populate(store, 1000)
    store.persist()
    fresh = RDFLibStore()
    fresh.load(project_root)
    t0 = time.perf_counter()
    fresh.add([Triple("cfa:F-999999", "rdf:type", "cfa:Feature")])
    fresh.persist()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return BenchmarkResult(
        name="incremental_update",
        elapsed_ms=elapsed_ms,
        budget_ms=None,
        detail="1k base + 1 triple add + persist",
    )


def benchmark_shacl_validate(project_root: Path, triples: int) -> BenchmarkResult:
    store = RDFLibStore()
    store.load(project_root)
    _populate(store, triples)
    shapes = load_shapes(project_root, include_l3=False, strict=True)
    shape_file = project_root / "_shapes_for_bench.ttl"
    shape_file.write_text(shapes.serialize(format="turtle"), encoding="utf-8")
    t0 = time.perf_counter()
    report = store.validate(shape_graph=shape_file)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return BenchmarkResult(
        name="shacl_validate",
        elapsed_ms=elapsed_ms,
        budget_ms=None,
        detail=f"{triples} triples · violations={report.violation_count}",
    )


def benchmark_owl_rl_infer(project_root: Path, triples: int) -> BenchmarkResult:
    onto = load_ontology(project_root, include_l3=False, strict=True)
    store = RDFLibStore()
    store.load(project_root)
    _populate(store, triples)
    # Pull into a plain Graph for infer() — synth triples land in the
    # default graph, so iterating the store gives us those plus the
    # ontology axioms (which we exclude by re-passing them separately).
    from rdflib import Graph
    data = Graph()
    for s, p, o, _g in store:
        data.add((URIRef(s), URIRef(p), Literal(o) if not o.startswith("http") else URIRef(o)))
    t0 = time.perf_counter()
    derived = infer(data, onto)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return BenchmarkResult(
        name="owl_rl_infer",
        elapsed_ms=elapsed_ms,
        budget_ms=None,
        detail=f"{triples} triples → {len(derived)} derived",
    )


def benchmark_single_sparql_query(
    project_root: Path, triples: int,
) -> BenchmarkResult:
    store = RDFLibStore()
    store.load(project_root)
    _populate(store, triples)
    sparql = (
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "SELECT ?m ?f WHERE { ?m a cfa:Module ; cfa:implements ?f } LIMIT 100"
    )
    t0 = time.perf_counter()
    for _ in range(_QUERY_REPEAT):
        store.query(sparql)
    elapsed_ms = ((time.perf_counter() - t0) * 1000) / _QUERY_REPEAT
    return BenchmarkResult(
        name="single_sparql_query",
        elapsed_ms=elapsed_ms,
        budget_ms=None,
        detail=f"{triples} triples · mean of {_QUERY_REPEAT} runs",
    )


def _attach_budgets(
    results: list[BenchmarkResult],
    budget: dict[str, Any],
) -> list[BenchmarkResult]:
    out: list[BenchmarkResult] = []
    for r in results:
        entry = budget.get(r.name)
        budget_ms = (
            float(entry["max_ms"])
            if isinstance(entry, dict) and "max_ms" in entry
            else None
        )
        out.append(
            BenchmarkResult(
                name=r.name,
                elapsed_ms=r.elapsed_ms,
                budget_ms=budget_ms,
                detail=r.detail,
            ),
        )
    return out


def run_benchmarks(
    project_root: str | Path,
    budget: dict[str, Any] | None = None,
) -> list[BenchmarkResult]:
    """Run the full benchmark suite under ``project_root`` (workdir for the
    transient ``docs/.doc-graph/`` storage) and attach budget thresholds."""
    root = Path(project_root).resolve()
    (root / "docs").mkdir(parents=True, exist_ok=True)
    budget = budget or DEFAULT_BUDGET
    rebuild_cfg = budget.get("full_rebuild", {})
    rebuild_docs = int(rebuild_cfg.get("docs", 100)) if isinstance(rebuild_cfg, dict) else 100
    shacl_cfg = budget.get("shacl_validate", {})
    shacl_n = int(shacl_cfg.get("triples", 5000)) if isinstance(shacl_cfg, dict) else 5000
    infer_cfg = budget.get("owl_rl_infer", {})
    infer_n = int(infer_cfg.get("triples", 5000)) if isinstance(infer_cfg, dict) else 5000

    raw = [
        benchmark_full_rebuild(root, rebuild_docs),
        benchmark_incremental_update(root),
        benchmark_shacl_validate(root, shacl_n),
        benchmark_owl_rl_infer(root, infer_n),
        benchmark_single_sparql_query(root, 1000),
    ]
    return _attach_budgets(raw, budget)


def format_report(
    results: list[BenchmarkResult],
    budget: dict[str, Any] | None = None,
) -> str:
    """Render a human-readable table of benchmark outcomes."""
    lines = [
        "CataForge KG benchmark report",
        "=" * 60,
        f"{'metric':<25} {'elapsed':>10} {'budget':>10}  status",
        "-" * 60,
    ]
    warns: list[str] = []
    for r in results:
        budget_str = f"{r.budget_ms:.0f}ms" if r.budget_ms is not None else "—"
        lines.append(
            f"{r.name:<25} {r.elapsed_ms:>8.1f}ms {budget_str:>10}  {r.status}",
        )
        lines.append(f"    {r.detail}")
        if r.status == "WARN":
            warns.append(r.name)
    lines.append("-" * 60)
    if warns and budget is not None:
        threshold = budget.get("oxigraph_autoswap_threshold_triples")
        lines.append(
            f"WARN · {len(warns)} metric(s) over budget: {', '.join(warns)}. "
            f"Consider switching to the oxigraph backend "
            f"(threshold ~= {threshold} triples).",
        )
    else:
        lines.append("All metrics within budget (or unbudgeted).")
    return "\n".join(lines)
