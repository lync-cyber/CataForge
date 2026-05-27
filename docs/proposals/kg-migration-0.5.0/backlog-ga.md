# KG 0.5.0 GA Backlog

Tracks work remaining after the P0 implementation landed on branch
`claude/knowledge-graph-progress-LNzCP`. Reference: the original
design lives in this directory's task-1 through task-7 documents.

## Completed (P0)

| ID | Deliverable | Files |
|----|-------------|-------|
| W1 | `threading.Lock` write-lock on `KnowledgeGraph.transaction()` | `facade.py` |
| W3 | High-level CRUD: `add_entity` / `update_entity` / `delete_entity` / `add_relation` / `remove_relation` on `TransactionContext` | `transaction.py`, `_quads.py` |
| C6 | `cataforge kg snapshot` — NQuads dump + `.meta.json` sidecar | `snapshot.py`, `kg_cmd.py` |
| C7 | `cataforge kg rollback SNAPSHOT_PATH` — restore from snapshot | `snapshot.py`, `kg_cmd.py` |
| V1 | `cataforge kg repair` — remove ghosts + re-ingest missing per doc_type | `repair.py`, `kg_cmd.py` |
| T1 | Group A test coverage 15/15 rows (A3/A4/A7/A8/A12/A14/A15 added) | `test_group_a_remaining.py` |
| — | Error hierarchy: `KGTransactionConflictError`, `KGValidationError`, `KGEntityNotFoundError` | `_errors.py` |
| — | Quad construction extracted to shared module | `_quads.py` |

Test count: 154 passed, 4 skipped (codegen CLI).

## P1 — high-value user-visible features

| ID | Task | Scope | Depends on |
|----|------|-------|------------|
| C1 | `cataforge kg query` CLI (SPARQL-only; NL deferred) | ~200 LOC: SPARQL parse, output format dispatch (table/json/turtle), timeout via `KGConfig.query_timeout` | — |
| C2 | `cataforge kg trace` CLI | ~250 LOC: wrap `TraceAPI.from_requirement` + `bidirectional_coverage`; `--output mermaid` renderer | — |
| Q1 | `QueryAPI.api()` / `.page()` typed accessors | ~30 LOC: 1:1 with existing `feature()` / `module()` pattern | — |
| Q2 | `QueryAPI._depends_on()` public + `TraceAPI.stale_dependencies()` integration test | ~50 LOC: `_depends_on` already implemented, needs public exposure + test | — |
| H1 | `TechStack` entity: core.yaml schema update + ingest codemod for arch §1.4 | ~150 LOC: schema slot + `ingest/migrate.py` extractor | — |

## P2 — stability and compliance

| ID | Task | Scope | Depends on |
|----|------|-------|------------|
| W2 | SHACL runtime bridge (pyoxigraph → rdflib) **or** formal deferral to 0.6.0 | ~300 LOC if implemented; 0 LOC if documented as deferred | upstream pyoxigraph API |
| S2 | Shim `DeprecationWarning` acknowledgment quota: define metric + CI gate | ~100 LOC | — |
| S3 | Confirm doc-review `check_xref` uses KG path when active (no regex fallback) | ~100 LOC audit + test | Q2 |
| T2 | Golden-file regression fixtures: pin reference reports under `tests/golden/kg/` | ~200 LOC | — |
| T3 | Promote pyoxigraph to hard dependency; remove `skipif` test gates | ~50 LOC: `pyproject.toml` + grep-replace markers | — |
| X1 | `_shim.py` export audit: confirm re-export from `cataforge.kg.__init__` | ~50 LOC | — |

## P3 — deferrable to post-GA

| ID | Task | Scope | Notes |
|----|------|-------|-------|
| C3 | `cataforge kg add` CLI | ~150 LOC | agents use Python API |
| C4 | `cataforge kg update` CLI | ~100 LOC | agents use Python API |
| C5 | `cataforge kg delete` CLI | ~120 LOC | agents use Python API |
| C8 | `cataforge kg diff` (semantic diff between snapshots) | ~200 LOC | operational diagnostic |
| X2 | 0.4.x → 0.5.0 migration guide | ~1000 LOC docs | ships with GA release |
| O1 | Natural-language query LLM adapter | ~300 LOC | deferred to 0.6.0+ |
| O3 | Export templates for ui-spec / dev-plan doc_types | ~100 LOC per type | incremental |

## Dependency graph

```
C1 (kg query CLI) ─────────────────────────────┐
C2 (kg trace CLI) ─────────────────────────────┤
Q1 (api/page accessors) ───────────────────────┤
Q2 (_depends_on public) ──→ S3 (xref audit) ──┤
H1 (TechStack schema) ────────────────────────┤
                                               ├──→ GA gate
T2 (golden-file) ─────────────────────────────┤
T3 (hard dependency) ─────────────────────────┤
W2 (SHACL decision) ──────────────────────────┤
S2 (deprecation quota) ───────────────────────┘
```

## GA exit conditions

All must be verifiable, never time-based:

1. `kg_ingestion_completeness` ERROR-enforced across all active doc_types
2. KG → Markdown byte-identical for every active doc_type
3. Group A golden-file regression passes (15/15 rows)
4. Both waterfall and agile process-model paths green
5. `kg_active_doc_types` covers all project doc_types (beyond the current prd/arch/test)
6. Legacy regex code paths removed from doc-review for active doc_types
7. Shim deprecation warning quota met

## Sizing summary

| Priority | Estimated LOC | Suggested sub-PRs |
|----------|---------------|--------------------|
| P1 | ~680 | 2 (CLI query+trace / QueryAPI+TechStack) |
| P2 | ~800 | 1–2 (SHACL decision + audit + test hardening) |
| P3 | ~1870 | as needed |
| **GA total** | **~1480** (P1+P2) | **3–4 sub-PRs** |
