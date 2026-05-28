# KG 0.5.0 GA Backlog

Tracks work remaining after the P0 implementation landed. Reference:
the original design lives in this directory's task-1 through task-7
documents.

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

## Completed (P1)

| ID | Deliverable | Files |
|----|-------------|-------|
| C1 | `cataforge kg query` CLI — SPARQL SELECT/ASK/CONSTRUCT with table/json/turtle output, `--limit`, `.sparql` file input | `kg_cmd.py`, `errors.py` |
| C2 | `cataforge kg trace` CLI — traceability chain with downstream/upstream/both, table/json/mermaid output, `--coverage` global matrix | `kg_cmd.py` |
| Q1 | `QueryAPI.api()` / `.page()` typed accessors — hit-path tests confirmed (accessors landed in sub-PR 5) | `test_facade.py` |
| Q2 | `QueryAPI.depends_on()` promoted to public API + `TraceAPI.stale_dependencies()` direct integration tests | `query.py`, `_shim.py`, `test_facade.py`, `test_group_a_remaining.py` |
| H1 | `TechStack` entity: standard `TS-NNN` ingest via `entity_extract.py` + `extra_slots` enrichment, SPARQL/Jinja2 export templates, `narrative_body` + `stack_layers` slots, `_quads.py` multivalued extra_slots support | `entity_extract.py`, `_quads.py`, `writer.py`, `hydrator.py`, `pipeline.py`, `techstack.sparql`, `techstack.md.j2`, `core.yaml` |

Test count: 197 passed, 4 skipped (codegen CLI).

## Completed (P2)

| ID | Deliverable | Files |
|----|-------------|-------|
| T3 | Promote pyoxigraph + linkml-runtime to hard dependencies; remove 22 `skipif` test gates | `pyproject.toml`, 22 test files |
| X1 | `render_entity` re-exported from `cataforge.kg.__init__`; public API smoke tests | `__init__.py`, `test_public_api.py` |
| T2 | Golden-file regression fixtures: 18 reference `.md` + 2 hash manifests under `tests/golden/kg/` | `test_golden_regression.py`, `tests/golden/kg/` |
| S3 | doc-review `check_xref` + `check_bidirectional_coverage` KG dispatch integration tests | `test_doc_review_kg_dispatch.py` |
| S2 | Shim `DeprecationWarning` quota CI gate (baseline 0) | `check_deprecation_quota.py`, `test.yml`, `run_local.py` |
| W2 | SHACL runtime bridge: pyoxigraph → rdflib conversion + pyshacl validation | `validate.py`, `test_shacl_bridge.py`, `pyproject.toml` `[shacl]` extra |

Test count: 212 passed, 4 skipped (codegen CLI).

## Completed (post-GA P3 batch 1)

| ID | Deliverable | Files |
|----|-------------|-------|
| C3 | `cataforge kg add` CLI — class / title / source-doc / source-section / content-hash / project-id / repeatable --slot + --relation; auto-detects unique Project; idempotent on same content-hash | `kg_cmd.py`, `test_cli_crud.py` |
| C4 | `cataforge kg update` CLI — partial slot update with content-hash short-circuit; requires at least one change field | `kg_cmd.py`, `test_cli_crud.py` |
| C5 | `cataforge kg delete` CLI — interactive confirm with --yes bypass; --cascade to remove incoming edges | `kg_cmd.py`, `test_cli_crud.py` |

Test count: 226 passed (14 new CRUD tests; full kg suite 230 passed).

## P3 — deferrable to post-GA

| ID | Task | Scope | Notes |
|----|------|-------|-------|
| C8 | `cataforge kg diff` (semantic diff between snapshots) | ~200 LOC | operational diagnostic |
| X2 | 0.4.x → 0.5.0 migration guide | ~1000 LOC docs | ships with GA release |
| O1 | Natural-language query LLM adapter | ~300 LOC | deferred to 0.6.0+ |
| O3 | Export templates for ui-spec / dev-plan doc_types | ~100 LOC per type | incremental |

## Dependency graph

```
✅ C1 (kg query CLI) ──────────────────────────┐
✅ C2 (kg trace CLI) ──────────────────────────┤
✅ Q1 (api/page accessors) ────────────────────┤
✅ Q2 (depends_on public) ──→ ✅ S3 (xref)    ┤
✅ H1 (TechStack ingest) ─────────────────────┤
✅ T2 (golden-file) ──────────────────────────┤
✅ T3 (hard dependency) ──────────────────────┤──→ GA gate
✅ W2 (SHACL bridge) ─────────────────────────┤
✅ S2 (deprecation quota) ────────────────────┤
✅ X1 (export audit) ─────────────────────────┘
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

| Priority | Estimated LOC | Status |
|----------|---------------|--------|
| P1 C1+C2+Q1+Q2+H1 | ~680 delivered | done |
| P2 T3+X1+T2+S3+S2+W2 | ~500 delivered | done |
| P3 batch 1 C3+C4+C5 | ~370 delivered | done |
| P3 remaining (C8+X2+O1+O3) | ~1500 | post-GA |
| **GA remaining** | **0** | **all P2 complete** |
