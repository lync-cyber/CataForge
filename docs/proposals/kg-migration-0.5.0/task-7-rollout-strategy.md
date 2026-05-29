# Task 7 — KG Migration Rollout Strategy & Risk Control

> KG Migration 0.5.0 · Agent-T7 产出

---

## §7.1 Phased Release Plan

### Overview

The migration proceeds in **two phases**: Alpha (build + cutover) and GA (stabilize + release). The earlier draft of this section had three phases including a Beta dual-track period; that has been collapsed because the project chose a full-cutover model (no Markdown loader fallback) at proposal-review time. Within Alpha, a **strict linear sub-PR sequence** drives implementation. Each phase gate is a **verifiable condition set**, not a calendar date.

The feature flag that governs cutover is `KGConfig.kg_active_doc_types: set[str]` — a set of doc_type strings for which the KG path is authoritative. Empty set = legacy loader for all reads (the pre-Alpha state). The Alpha cutover progresses by populating this set, doc_type by doc_type. Once the set covers all in-scope doc_types and the doctor gate is ERROR for at least one full reconcile cycle, Alpha exits to GA.

---

### Phase 1 · Alpha (Build + Cutover)

**Scope:** end-to-end vertical slice covering three doc_types (prd, arch, test) and the entity chain Requirement → Component → TestCase, with both waterfall (Phase) and agile (Sprint) process-model paths exercised. Delivered as a strict linear sub-PR sequence; each sub-PR must merge to main before the next opens. No dual-track running; cutover is per-doc_type via `kg_active_doc_types`.

**Entry Condition (Alpha kickoff PR):**
- Issue [CataForge#142](https://github.com/lync-cyber/CataForge/issues/142) (spike findings) has actionable items 1.1 / 1.2 / 1.3 resolved into concrete schema/doc edits queued for sub-PR 1.
- `linkml-runtime>=1.11.1` and `pyoxigraph>=0.5.8` are pinned in `pyproject.toml`.
- `PYTHONIOENCODING=utf-8` is wired into the codegen invocation (Windows GBK console gotcha from spike-1 1.4).

**Sub-PR sequence (strict linear, each merged before the next opens):**

1. **Sub-PR 1 · `schema + codegen`** — merge corrected `core.yaml` / `governance.yaml` (with spike-1 fixes applied); add `scripts/codegen_kg_schema.py` that runs `gen-pydantic` / `gen-shacl` and writes generated artefacts to `src/cataforge/domain/kg/_generated/`; bootstrap `rdfs:subClassOf` triples generated from `core.yaml` `is_a` chain (per spike-2 2.1). No runtime code paths touched.
2. **Sub-PR 2 · `store + init`** — `src/cataforge/domain/kg/store.py` (Oxigraph + memory backends), `cataforge kg init` CLI, `KGConfig` dataclass with `kg_active_doc_types: set[str] = field(default_factory=set)` defaulting to empty. Verified by an integration test that opens an empty store, loads the bootstrap schema triples, and runs a no-op SPARQL ASK. No business data ingested.
3. **Sub-PR 3 · `import codemod`** — `scripts/migrate_docs_to_kg.py` per §7.2; ingests prd / arch / test doc_types only; produces `cataforge kg validate` reports with zero `missing` entries on a hand-crafted fixture project covering both waterfall and agile process models. Adds `kg_active_doc_types` config field but does **not** yet flip it; reads still go through legacy loader.
4. **Sub-PR 4 · `export round-trip`** — Task 4 export pipeline (`cataforge kg export`); proves byte-identical idempotency across two consecutive exports; KG-to-Markdown output diff-clean against original source for the fixture project. Still no read-side change.
5. **Sub-PR 5 · `cutover + doctor gate ERROR`** — Task 6 §6.2 call-site migration for the 15 Group A call points; shim layer dispatches on `doc_type in KGConfig.kg_active_doc_types` (per Task 5 §5.5 and Task 6 §6.5); `cataforge doctor kg_ingestion_completeness` gate added at **ERROR severity** in this same PR (per the explicit decision recorded in [README §User decisions](README.md)). Default config in this PR sets `kg_active_doc_types = {"prd", "arch", "test"}` for projects opting in; projects can roll back by removing entries.

**Exit Condition (Alpha → GA):**
- All five sub-PRs merged to main and tagged.
- `cataforge doctor kg_ingestion_completeness` gate has been ERROR-enforced (not WARN) for at least one full `cataforge kg reconcile` cycle on the fixture project with zero failures.
- KG → Markdown export round-trip: byte-identical on two consecutive runs for every doc_type in `kg_active_doc_types`.
- SHACL validation (`pyshacl`, optional) reports zero critical violations on the ingested fixture graph.
- All 15 Group A call points return identical results via KG path as legacy path on the fixture project (one-shot regression test recorded as a golden file).
- Both waterfall (`process_model = waterfall`) and agile (`process_model = agile`) test projects pass end-to-end (per the explicit dual-coverage decision in [README §User decisions](README.md)).

**Rollback Trigger:**
- `kg_ingestion_completeness` gate reports completeness below the configured threshold (default 95%) after two consecutive `cataforge kg repair` attempts on any opted-in project.
- Any agent produces a semantically incorrect output traced to a KG query vs. legacy Markdown difference on a previously-passing fixture reference.
- A pyoxigraph or oxrdflib version upgrade causes a deserialization error when opening an existing RocksDB store.
- Rollback action: remove the affected `doc_type` from `KGConfig.kg_active_doc_types` (per-doc_type flag granularity, per [README §User decisions](README.md)); this reverts reads for that doc_type to the legacy loader without affecting other doc_types. If the regression is systemic, remove all entries from the set and restore the KG snapshot per §7.3.

**Phase Deliverables (cumulative across sub-PRs 1–5):**
- `src/cataforge/domain/kg/_generated/*` — codegen output (gitignored; regenerated from `core.yaml`).
- `src/cataforge/domain/kg/` — `store.py`, `config.py`, `query.py`, `trace.py`, `transaction.py`.
- `src/cataforge/domain/kg/export/` — Task 4 pipeline.
- `scripts/codegen_kg_schema.py` — wraps `gen-pydantic` / `gen-shacl` with `PYTHONIOENCODING=utf-8`.
- `scripts/migrate_docs_to_kg.py` — data migration script (see §7.2).
- `cataforge doctor` integration: `kg_ingestion_completeness` gate at ERROR severity (sub-PR 5).
- `cataforge kg init` / `import` / `export` / `validate` / `repair` / `reconcile` / `snapshot` / `rollback` / `diff` CLI subcommands (Task 5 §5.1 subset).
- Shim layer in `src/cataforge/domain/kg/_shim.py` dispatching on `kg_active_doc_types`.
- Fixture project under `tests/fixtures/kg-vertical-slice/` covering prd / arch / test in both waterfall and agile variants.

---

### Phase 2 · GA (Stabilize + Release)

**Scope:** Production stabilization, deprecation enforcement, and `v0.5.0` release tag. Legacy Markdown loader paths remain in tree as fallback emergency exit but are not the default for any in-scope doc_type.

**Entry Condition:**
- Phase 1 exit conditions all satisfied.
- 100% of organisations piloting Alpha are on `coverage_mode = strict`.
- `cataforge kg reconcile` has been run at least 20 times across all opted-in projects with zero unresolved divergences.
- Deprecation notice for `docs/.doc-index.json` as sole source of truth has been in `CHANGELOG` for at least one prior release.

**Exit Condition:**
- `cataforge docs index` (legacy) is removed from the default flow; `cataforge kg ingest` is the canonical indexing path.
- `docs/.doc-index.json` is retained as a derived cache only; `cataforge kg export-index` regenerates it from KG.
- All tests pass with `store_backend = "oxigraph"` in CI (RocksDB path covered alongside the `memory` backend used elsewhere).
- `cataforge doctor` reports no legacy-compat annotated call sites remaining.
- Release tag `v0.5.0` is created; CHANGELOG entry is complete.

**Rollback Trigger (post-GA):**
- A critical correctness regression is reported and confirmed affecting any GA user within the first post-release reconcile cycle — triggers a hotfix branch, not a full rollback. Full rollback (to 0.4.x) only if the regression is systemic (all projects affected, no patch available).

**Phase Deliverables:**
- Removal PRs for legacy `indexer.py` Markdown-scan path, `iter_markdown_headings` fallback, `check_bidirectional_coverage` regex implementation, `check_xref` regex implementation.
- `cataforge kg export-index` CLI (KG → `.doc-index.json` derived cache for backward compatibility with external tools).
- v0.5.0 release tag + CHANGELOG.
- Migration guide for end-users (`docs/guides/migrate-0.4-to-0.5.md`).

---

## §7.2 Data Migration Script Design

### Scope

The script targets business documents only: `docs/{doc_type}/*.md` where `doc_type` is one of the 14 types listed in Task 1 §1.6. Framework assets (`.cataforge/skills/`, `.cataforge/agents/`, etc.) are left untouched regardless of any Task 3 governance decision — they remain file-system-resident.

If Task 3 decides that a governance entity (e.g., skill dependency or agent dispatch rule) enters the graph, a separate `scripts/migrate_framework_assets_to_kg.py` script will be produced under that task's scope. This script is **not** responsible for framework assets.

### Entity ID Pattern Recognition

The script uses the 9 entity types from Task 1 §1.6:

| ID Pattern | Entity Type |
|------------|-------------|
| `F-NNN` | Feature |
| `AC-NNN` | AcceptanceCriteria |
| `M-NNN` | Module |
| `API-NNN` | APIContract |
| `E-NNN` | Entity |
| `C-NNN` | Component |
| `P-NNN` | Page |
| `T-NNN` | Task |
| `TC-NNN` / `SR-NNN` | TestCase / SprintReviewIssue |

### Data Integrity Validation

After ingestion the script verifies:

1. **Entity count**: count of extracted entities per type matches count of ID-pattern matches found during scan.
2. **Relation count**: count of extracted triples with domain-specific predicates (`:traces`, `:implementedBy`, `:verifiedBy`, etc.) matches the cross-reference pairs found in source documents.
3. **Traceability completeness**: every entity that appeared in a `context_load` or `dep` field in `.doc-index.json` has a corresponding KG triple linking the dependent entity.
4. **Key-field hash compare**: for each entity, the SHA-256 of the source section text (extracted from Markdown) matches the `content_hash` stored in the KG triple. Mismatches are reported as integrity errors.

### Idempotency

- **Dedup**: before writing, the script issues a SPARQL ASK to check whether a triple with the same subject+predicate+object already exists. Existing triples are skipped, not duplicated.
- **ID stability**: entity IRIs are derived deterministically from the entity ID string (`<base_ns>{entity_id}`, e.g., `cf:F-001`). Running the script twice on unchanged source produces identical IRIs.
- **Timestamp handling**: the `schema:dateModified` triple is set from the source file's `mtime`. On re-run, if the file `mtime` is unchanged, the triple update is skipped. If `mtime` has changed, the old `dateModified` triple is deleted and replaced.

### Core Logic Pseudocode

```pseudocode
function migrate_docs_to_kg(project_root, kg_store, dry_run=False):
    doc_type_map = load_doc_type_map(project_root)  # from framework.json
    stats = {entity_count: 0, relation_count: 0, skipped: 0, errors: []}

    # PHASE 1: SCAN — enumerate all business docs
    doc_files = []
    for doc_type, subdir in doc_type_map.items():
        doc_files += glob(project_root / "docs" / subdir / "*.md")

    # PHASE 2: PARSE — extract frontmatter + headings + item IDs
    parsed_docs = []
    for doc_file in doc_files:
        raw = read_file(doc_file)
        frontmatter = extract_yaml_frontmatter(raw)   # --- block at top of file
        headings = extract_headings_with_line_ranges(raw)
        doc_id = frontmatter.get("doc_id") or infer_doc_id(doc_file.name)
        parsed_docs.append({
            doc_id: doc_id,
            doc_type: frontmatter.get("doc_type"),
            file_path: doc_file,
            mtime: doc_file.stat().st_mtime,
            sections: headings,
            raw: raw,
        })

    # PHASE 3: BUSINESS-ENTITY EXTRACTION
    entities = []
    ITEM_ID_RE = re.compile(r'\b(F|AC|M|API|E|C|P|T|TC|SR)-\d{3}\b')
    for doc in parsed_docs:
        for section in doc.sections:
            section_text = slice_text(doc.raw, section.line_start, section.line_end)
            for match in ITEM_ID_RE.finditer(section_text):
                entity_id = match.group(0)
                if not already_ingested(kg_store, entity_id, doc.mtime):
                    entities.append({
                        id: entity_id,
                        type: id_prefix_to_type(entity_id),
                        source_doc: doc.doc_id,
                        source_section: section.heading,
                        content_hash: sha256(section_text),
                        raw_text: section_text,
                        mtime: doc.mtime,
                    })

    # PHASE 4: TRACEABILITY RELATION EXTRACTION
    relations = []
    XREF_RE = re.compile(r'([\w-]+)#§([\d]+\.(?:F|AC|M|API|E|C|P|T|TC|SR)-\d{3})')
    for doc in parsed_docs:
        for match in XREF_RE.finditer(doc.raw):
            target_doc_id = match.group(1)
            target_ref = match.group(2)
            source_entity = infer_enclosing_entity(doc, match.start())
            if source_entity and target_ref:
                relations.append({
                    subject: source_entity.id,
                    predicate: infer_predicate(source_entity.type, target_ref),
                    object: extract_entity_id(target_ref),
                    source_doc: doc.doc_id,
                })

    # PHASE 5: WRITE GRAPH
    if not dry_run:
        for entity in entities:
            write_entity_triples(kg_store, entity)
            stats.entity_count += 1
        for relation in relations:
            if not triple_exists(kg_store, relation):
                write_relation_triple(kg_store, relation)
                stats.relation_count += 1
            else:
                stats.skipped += 1

    # PHASE 6: VERIFY
    verify_entity_count(kg_store, stats.entity_count)
    verify_relation_count(kg_store, stats.relation_count)
    verify_traceability_completeness(kg_store, project_root)
    verify_content_hashes(kg_store, entities)

    return stats
```

```python
def already_ingested(kg_store, entity_id: str, file_mtime: float) -> bool:
    """
    Returns True if entity exists in the graph AND the stored mtime
    matches the current file mtime — meaning the source is unchanged.
    """
    iri = entity_iri(entity_id)
    result = kg_store.query(f"""
        ASK {{
            <{iri}> <{CF}sourceMtime> ?mtime .
            FILTER(xsd:decimal(?mtime) = {file_mtime})
        }}
    """)
    return bool(result)

def infer_predicate(source_type: str, target_ref: str) -> str:
    """Map (source entity type, target entity ID prefix) to a KG predicate IRI."""
    target_prefix = re.match(r'[A-Z]+', target_ref).group(0)
    PREDICATE_MAP = {
        ("Module",       "F"):   CF + "implementsFeature",
        ("Component",    "F"):   CF + "implementsFeature",
        ("Page",         "F"):   CF + "implementsFeature",
        ("Task",         "M"):   CF + "assignedToModule",
        ("Task",         "API"): CF + "usesAPI",
        ("Task",         "C"):   CF + "implementsComponent",
        ("TestCase",     "T"):   CF + "verifiesTask",
        ("TestCase",     "AC"):  CF + "validatesCriteria",
        ("APIContract",  "F"):   CF + "traces",
    }
    return PREDICATE_MAP.get((source_type, target_prefix), CF + "references")
```

---

## §7.3 Rollback Plan

### State Snapshot Mechanism

Before running the migration script, a snapshot is captured:

1. **KG data snapshot**: `cataforge kg snapshot --output .cataforge/backups/kg-pre-migration-{timestamp}.oxigraph.tar.gz` — creates a compressed archive of the RocksDB store directory.
2. **Index file backup**: copy `docs/.doc-index.json` to `docs/.doc-index.json.bak-{timestamp}`.
3. **Markdown source backup**: for any Markdown file that `cataforge kg export` will overwrite (KG → Markdown derived exports), copy the original to `docs/.markdown-backup-{timestamp}/`.

The `{timestamp}` token is an ISO-8601 UTC string (`YYYYMMDDTHHMMSSZ`). Backups are retained until explicitly deleted by the operator.

### Rollback Triggers

Three distinct event classes that trigger rollback:

1. **Data-integrity failure**: `cataforge doctor kg_ingestion_completeness` reports completeness below the configured threshold (default 95%) after two consecutive repair attempts (`cataforge kg repair`). This indicates that the migration script produced an incomplete or corrupt graph that automated repair cannot resolve.

2. **Agent semantic divergence**: a `cataforge kg compare-read` sampling run reports that a KG SPARQL query and the legacy `loader.extract()` call for the same reference return materially different content (diff > configurable similarity threshold, default 0.05 Jaccard distance on section tokens). This indicates the KG is not an accurate representation of the Markdown source.

3. **Dependency library failure**: a pyoxigraph or oxrdflib version upgrade causes a deserialization error when opening an existing RocksDB store, and the upstream library does not provide a migration path within the same release cycle.

### Rollback Operation Steps

1. Stop all agents and any running `cataforge` background processes.
2. Verify the backup archive is intact: `cataforge kg snapshot --verify .cataforge/backups/kg-pre-migration-{timestamp}.oxigraph.tar.gz`.
3. Remove the corrupt or diverged KG store: `rm -rf .cataforge/kg/store/`.
4. Restore the KG snapshot: `cataforge kg snapshot --restore .cataforge/backups/kg-pre-migration-{timestamp}.oxigraph.tar.gz`.
5. Restore the index file: `cp docs/.doc-index.json.bak-{timestamp} docs/.doc-index.json`.
6. Restore any overwritten Markdown files from `docs/.markdown-backup-{timestamp}/` to their original paths.
7. Revert agent `Input Contract` SPARQL calls to legacy `cataforge docs load` CLI calls (via `git revert` of the agent migration commit, or by re-deploying the 0.4.x skill set).
8. Run post-rollback validation (see below).

### Post-Rollback State Validation

After completing rollback steps, verify:

- `cataforge docs load prd#§1` returns the expected section text (smoke test on one known reference per doc type).
- `cataforge docs validate` exits 0 with no new errors beyond any pre-migration known issues.
- `cataforge doctor` shows no `kg_*` gates in `FAIL` state (KG gates should be absent or disabled after rollback to 0.4.x mode).
- Git status confirms no uncommitted partial-migration artefacts remain in `src/cataforge/domain/kg/` that would affect the next migration attempt.

---

## §7.4 Technical Risk Register

Probability / impact reflect the full-cutover model chosen for Alpha (no Markdown-loader fallback during normal operation; flag rollback per doc_type is the only escape hatch).

| # | Risk | Probability | Impact | Mitigation | Detection Signal |
|---|------|-------------|--------|------------|-----------------|
| R-01 | **Data migration incompleteness**: entity extraction misses entities in non-standard section layouts (e.g., items nested inside HTML comment blocks, or in code fences within a section) | M | H | Use a two-pass extraction: first pass regex on stripped-code-block text, second pass over raw text with a stricter context filter; report unmatched known entity IDs (from `.doc-index.json` `items` field) as warnings | `kg_ingestion_completeness` gate below threshold; entity count in KG < entity count in `.doc-index.json` |
| R-02 | **KG library selection change / deprecation**: pyoxigraph primary author (@Tpt) abandons or significantly changes the API between 0.5.x and a future version, breaking the RocksDB store format | L | H | Pin `pyoxigraph>=0.5.8,<0.6` in `pyproject.toml`; maintain a `memory`-backend fallback for all queries; abstract the store behind `GraphRepository` so a backend swap is a single-file change | pyoxigraph GitHub repository shows archival or breaking-change release notes; wheel build failures on CI |
| R-03 | **Performance regression on large projects**: SPARQL queries over a large graph (thousands of entities) take longer than the legacy O(1) index lookup, degrading agent startup latency | M | M | Benchmark on a synthetic graph of 5,000+ triples before Alpha exit; add SPARQL LIMIT clauses to all agent startup queries; maintain `.doc-index.json` as a derived cache for the most frequent O(1) lookups | Agent startup latency measurement in CI exceeds 2× baseline; `cataforge kg benchmark` report |
| R-04 | **Agent/skill call-layer semantic divergence**: migrated SPARQL queries return subtly different content than `loader.extract()` for edge cases (e.g., multi-volume documents, split sections). **Elevated impact under full-cutover model** — no markdown fallback during normal operation means divergence hits production reads directly | H | H | Sub-PR 5 golden-file regression test compares every Group A call point's KG-path output vs. legacy-path output before flipping any doc_type into `kg_active_doc_types`; per-doc_type flag granularity allows rollback of one affected doc_type without disrupting others; `cataforge kg compare-read` sampling is retained as a periodic post-cutover audit (not a gating mechanism) | Golden-file test fails in sub-PR 5; `compare-read` post-cutover audit reports divergence; doc-review AI layer detects inconsistencies between KG-loaded context and expected content |
| R-05 | **Third-party extension compatibility**: downstream projects using custom `cataforge` plugins or directly importing `docs/.doc-index.json` as a data source break after it becomes a derived cache | M | M | Document `.doc-index.json` as derived-only with one release's advance warning; provide `cataforge kg export-index` as a backward-compatible regeneration command; survey known external integrations before GA | External projects report import errors or missing fields in `.doc-index.json` |
| R-06 | **Feature flag misconfiguration**: `KGConfig.kg_active_doc_types` is partially populated (e.g., `{"prd"}` but `arch` left out), causing cross-doc_type references to resolve inconsistently — a prd Feature reads from KG while the arch Component it implements reads from legacy loader | M | H | `cataforge kg validate` checks for cross-doc_type traceability fan-out: if any entity in an active doc_type has `cf:implements` / `cf:verifies` targeting a doc_type not in the active set, emit a configuration warning. doctor `kg_ingestion_completeness` gate runs separately per doc_type so a partial config still flags incomplete reads | `cataforge kg validate` configuration warning; `kg_ingestion_completeness` per-doc_type report; agent output references stale legacy-loader data for a related entity |
| R-07 | **Team / user learning cost for SPARQL**: agent authors and framework contributors unfamiliar with SPARQL may write incorrect or inefficient queries, introducing bugs in the migrated call layer | H | M | Provide a `GraphRepository` Python abstraction hiding SPARQL for the most common access patterns (`find_by_id`, `find_outbound`, `trace_to_root`); document SPARQL patterns in `docs/reference/kg-query-patterns.md`; code-review checklist item for any new SPARQL query | Code review flags invalid SPARQL; `cataforge kg validate-queries` reports parse errors; agent integration tests fail |
| R-08 | **Traceability extraction false-positive / false-negative**: `XREF_RE` in the migration script matches references that are in code fences, comments, or deprecated sections, generating incorrect KG edges; or misses references in non-standard formats | M | H | Apply the same `_strip_code_blocks` logic used in `checker.py`, but extend it to handle fenced blocks with language tags and inline code; add a second filter for `<!-- deprecated -->` sections; measure precision/recall against a hand-labeled reference set before Alpha exit | Traceability completeness metric shows unexpected edges; doc-review Layer 1 SPARQL checks report fewer or more covered entities than expected; human review of a sample KG export |
| R-09 | **`bool(QueryBoolean)` idiom mishandled**: pyoxigraph 0.5.x `Store.query()` returns a `QueryBoolean` object for ASK queries; comparing it to Python `True` with `==` silently always evaluates false. Surfaced by spike-2 finding 2.2. Affects every traceability-completeness gate (Task 5 §5.4 `KGTraceabilityBreakError`, Task 6 §6.4 A13 `check_bidirectional_coverage`, doctor `kg_ingestion_completeness`) | M | H | Wrap all ASK consumption through a single `ask(store, sparql) -> bool` utility in `src/cataforge/domain/kg/_ask.py` introduced in sub-PR 2; lint rule (or grep gate in pre-commit) rejects `query(... ASK ...) == True` patterns; document the idiom in `docs/reference/kg-query-patterns.md` | Pre-commit grep gate fires on disallowed pattern; integration test where doctor gate silently returns "pass" on a known-broken fixture |
| R-10 | **`rdfs:subClassOf` triples not materialized**: pyoxigraph has no OWL/RDFS entailment; `a/rdfs:subClassOf*` enumeration silently misses subclass instances if the class hierarchy is not loaded as Turtle triples at store init. Surfaced by spike-2 finding 2.1 | M | H | `cataforge kg init` (sub-PR 2) explicitly generates `rdfs:subClassOf` Turtle from `core.yaml` `is_a` chain and loads it into the store as part of bootstrap; integration test in sub-PR 2 asserts that querying for `Screen` instances returns at least one `Page` (a subclass) | Integration test fails in sub-PR 2; entity-enumeration SPARQL returns fewer rows than expected on a fixture with subclass instances |

---

## §7.5 Per-doc_type Rolling Cutover (Alpha Phase)

Replaces the earlier dual-track running plan. Under the full-cutover model chosen at proposal-review time, KG is the sole read path for any doc_type listed in `KGConfig.kg_active_doc_types`; legacy `loader.extract()` is the sole read path for any doc_type not in the set. There is no dual-write and no dual-read on the same doc_type. Cutover progresses by adding doc_types to the set, one or a few at a time.

### Write path

KG is always the source of truth for doc_types in `kg_active_doc_types`. Writes flow:

```
doc-gen finalize
  └─ Step 1: cataforge kg ingest --doc-file <path>     [KG write — authoritative]
  └─ Step 2: cataforge kg export --doc-file <path>     [KG → Markdown re-export, overwrites file with canonical form]
```

Steps 1–2 are wrapped in a single `cataforge kg commit --doc-file <path>` command, atomically (both succeed or both are rolled back via the KG snapshot taken at Step 1 start). For doc_types **not** in `kg_active_doc_types`, the legacy `cataforge docs index --doc-file <path>` write path continues unchanged (sub-PR 5 does not remove it).

### Consistency check: `cataforge kg reconcile`

`cataforge kg reconcile` is a periodic task designed to detect drift between KG and Markdown filesystem state. It runs **per-doc_type**, only against doc_types in `kg_active_doc_types`. Four steps:

1. **Scan**: enumerate business docs under `docs/{doc_type}/` for each `doc_type ∈ kg_active_doc_types`; extract entity IDs and cross-references from Markdown source.
2. **Compare**: issue SPARQL queries to retrieve all entities and relations stored in KG for that doc_type.
3. **Diff**: compute the symmetric difference. Any entity present in Markdown but absent in KG is a `missing` entry; any KG entity without a matching Markdown source is a `ghost` entry.
4. **Report**: write a structured diff report to `docs/.kg-reconcile-report.json` (per-doc_type sections). Exit non-zero if any `missing` or `ghost` entries exist.

```pseudocode
function kg_reconcile(project_root, kg_store, config):
    report = {timestamp: utc_now(), per_doc_type: {}}
    overall_divergence = 0

    for doc_type in config.kg_active_doc_types:
        md_entities = extract_all_entities_from_markdown(project_root, doc_type)
        md_relations = extract_all_relations_from_markdown(project_root, doc_type)

        kg_entities = sparql_select_all_entities(kg_store, doc_type)
        kg_relations = sparql_select_all_relations(kg_store, doc_type)

        missing_entities = md_entities - kg_entities
        ghost_entities   = kg_entities - md_entities
        missing_relations = md_relations - kg_relations
        ghost_relations   = kg_relations - md_relations

        divergence = len(missing_entities) + len(ghost_entities) \
                   + len(missing_relations) + len(ghost_relations)
        overall_divergence += divergence

        report.per_doc_type[doc_type] = {
            missing_entities: list(missing_entities),
            ghost_entities:   list(ghost_entities),
            missing_relations: list(missing_relations),
            ghost_relations:   list(ghost_relations),
            divergence_count: divergence,
        }

    report.overall_divergence_count = overall_divergence
    write_json(project_root / "docs/.kg-reconcile-report.json", report)

    if overall_divergence > 0:
        exit(1)
    exit(0)
```

`kg reconcile` is intended to run:
- After every `cataforge kg commit --doc-file <path>` (lightweight: only the updated doc's entities are compared).
- As a full-project sweep triggered by `cataforge doctor` or CI.

### Post-cutover audit: `cataforge kg compare-read`

Retained as a periodic **audit** (not a gating mechanism). For each active doc_type, takes a random sample of N references, executes both the KG SPARQL query and a one-off legacy `loader.extract()` call against the same Markdown source, and reports any pair where token Jaccard similarity < threshold (default 0.95). Audit fires diagnostic alarms but does not block writes; if alarms persist, the affected doc_type is removed from `kg_active_doc_types` (rollback step) and the divergence investigated.

### Decision points for doc_type promotion

A doc_type is added to `kg_active_doc_types` when:

- `cataforge kg validate` reports zero `missing` / `ghost` entries for that doc_type across at least one full reconcile cycle on a fixture project.
- Sub-PR 5's golden-file regression test for every Group A call point touching that doc_type passes.
- `cataforge kg compare-read --doc-type <doc_type>` audit run on the project's actual content reports zero alarms.

A doc_type is removed from `kg_active_doc_types` (rolled back to legacy loader) when:

- `cataforge kg reconcile` reports `missing` or `ghost` entries that two consecutive `cataforge kg repair` runs cannot resolve.
- `cataforge kg compare-read` audit reports persistent divergence alarms (≥2 alarms in 10 consecutive sample runs).
- An agent produces semantically incorrect output traced to that doc_type's KG path.

The set never reaches "all doc_types" by default in 0.5.0 — only `{"prd", "arch", "test"}` are in scope for Alpha. Other doc_types remain on the legacy loader through Alpha and GA and become candidates for 0.6.0 expansion.

---

## [依赖传递摘要]

**关键决策:**
- 两阶段发布（Alpha build+cutover / GA stabilize+release）均以可验证条件为门禁。Beta 双轨期已撤销 —— 项目在 proposal-review 时选择 full-cutover 模型，没有 markdown loader fallback。
- Alpha 内部走严格线性 sub-PR 序列（schema+codegen → store+init → import codemod → export round-trip → cutover+doctor gate ERROR），cutover 通过 `KGConfig.kg_active_doc_types: set[str]` 逐 doc_type 推进；Alpha 范围只覆盖 prd / arch / test 三个 doc_type，瀑布 + 敏捷双 process_model 同时验证。
- doctor `kg_ingestion_completeness` 硬门在 sub-PR 5 直接以 ERROR 级别合入（不走 WARN 过渡）。
- 数据迁移脚本采用六阶段管道（scan→parse→entity extraction→relation extraction→write→verify），幂等设计（IRI 由 entity ID 确定性派生，mtime 守卫跳过未变更实体），`coverage_mode=strict` 下只识别 `doc_id#§N.ITEM` 格式的跨文档引用。
- 回滚粒度 = 单 doc_type：从 `kg_active_doc_types` 中移除一个 doc_type 即可让该 doc_type 的读路径退回 legacy loader，其他 doc_type 不受影响。系统性问题才走完整 KG snapshot 恢复。
- 风险寄存器 10 条（原 R-06 双轨漂移撤销，新增 R-04 影响升级到 H/H、R-06 flag 配置不一致、R-09 `bool(QueryBoolean)` 习语、R-10 `rdfs:subClassOf` 显式物化）—— R-09 / R-10 来源于 [CataForge#142](https://github.com/lync-cyber/CataForge/issues/142) spike 发现。

**输出物路径/位置:** `docs/proposals/kg-migration-0.5.0/task-7-rollout-strategy.md`

**阻塞标记:** NONE
