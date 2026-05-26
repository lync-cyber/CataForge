# Task 7 — KG Migration Rollout Strategy & Risk Control

> KG Migration 0.5.0 · Agent-T7 产出

---

## §7.1 Phased Release Plan

### Overview

The migration proceeds in three phases. Each phase gate is a **verifiable condition set**, not a calendar date.

---

### Phase 1 · Alpha (Internal)

**Scope:** Business KG basic features + Markdown export verification. All testing is internal; no downstream projects migrate yet.

**Entry Condition:**
- Task 3 (schema design) LinkML YAML files are merged and passing `linkml lint`.
- Task 4 (agent/skill integration) has a passing stub-level test suite with `KGConfig.store_backend = "memory"`.
- Task 5 (migration script) reports `entity_count > 0` and `relation_count > 0` on the CataForge self-test fixture.

**Exit Condition:**
- All unit tests green (`pytest` exit code 0, no skips on KG-related test files).
- `cataforge doctor kg_ingestion_completeness` gate passes on the self-test fixture (entity count matches expected, no missing required fields).
- KG → Markdown export round-trip: exported Markdown files parse without error by the existing `loader.extract()` against every `doc_type` in `framework.json`.
- SHACL validation (`pyshacl`, optional) reports zero critical violations on the ingested self-test graph.
- Zero regressions on legacy `cataforge docs load` and `cataforge docs validate` CLI paths.

**Rollback Trigger:**
- Any previously passing `cataforge docs load` call begins returning empty results or errors on the self-test project.
- `kg_ingestion_completeness` gate reports completeness < 95% after two consecutive repair attempts.
- A security or correctness defect is found in the RocksDB write path that cannot be patched within the phase.

**Phase Deliverables:**
- `kg/schema/*.yaml` — LinkML schema for all 9 entity types.
- `src/cataforge/kg/` — `store.py`, `ingest.py`, `query.py`, `export.py`.
- `scripts/migrate_docs_to_kg.py` — data migration script (see §7.2).
- `cataforge doctor` integration: `kg_ingestion_completeness` gate.
- `cataforge kg export` CLI subcommand (KG → Markdown).
- Unit test suite (`tests/kg/`) with `memory` backend.

---

### Phase 2 · Beta (Gradual)

**Scope:** Agent/skill call-layer migration + dual-track running (KG-leading, Markdown as derived snapshot). A subset of downstream projects opts in.

**Entry Condition:**
- Phase 1 exit conditions all satisfied.
- At least one external project (not CataForge self) has successfully run `scripts/migrate_docs_to_kg.py` and passed `kg_ingestion_completeness`.
- `cataforge kg reconcile` command is implemented and produces a stable diff report (no panic on edge cases).
- `coverage_mode` configuration is implemented; `strict` is the enforced default.
- The `mention → strict` upgrade codemod (`scripts/upgrade_coverage_strict.py`) is implemented and has been run on at least the CataForge self-test fixture without errors.

**Exit Condition:**
- Double-write is active on at least two distinct projects for a sustained period (measured by `cataforge kg reconcile` runs, not calendar).
- `cataforge kg reconcile` reports zero entity-level divergence on all opted-in projects.
- All 16 call sites catalogued in Task 1 §1.3 have been migrated or explicitly annotated as "legacy-compat" with a tracked issue.
- `doc-review` Layer 1 uses SPARQL-based xref checks; false-positive and false-negative rates are measured and documented (any remaining known false cases are tracked).
- `cataforge kg compare-read` sampling alarm has been triggered zero times in the last N reconcile cycles (N = 10), confirming KG and Markdown read results are consistent.

**Rollback Trigger (during Beta):**
- `cataforge kg reconcile` reports entity-level divergence that cannot be resolved within one reconcile cycle.
- Any opted-in project's agent produces a semantically incorrect output traced to a KG query vs. legacy Markdown difference.
- `cataforge kg compare-read` alarm fires more than twice in 10 consecutive sampling cycles.

**Phase Deliverables:**
- Migrated agent `Input Contract` sections for all 6 SDLC roles (SPARQL-based loads).
- `cataforge kg reconcile` periodic task (see §7.5).
- `cataforge kg compare-read` sampling comparator.
- `mention → strict` codemod script.
- Updated `doc-review` Layer 1 (`checker.py`) using SPARQL xref and coverage checks.
- Updated `task-dep-analysis` skill using SPARQL graph traversal.
- Dual-track running documentation for opted-in projects.

---

### Phase 3 · GA (Formal Release)

**Scope:** Full switchover + removal of legacy Markdown-only tools. CataForge 0.5.0 release.

**Entry Condition:**
- Phase 2 exit conditions all satisfied.
- 100% of organisations piloting Beta are on `coverage_mode = strict`.
- `cataforge kg reconcile` has been run at least 20 times across all opted-in projects with zero unresolved divergences.
- All SPARQL-based replacements for previously Markdown-regex-based checks have documented equivalent or better precision (false-pos / false-neg rates measured in Beta).
- Deprecation notice for `docs/.doc-index.json` as sole source of truth has been in `CHANGELOG` for at least one prior release.

**Exit Condition:**
- `cataforge docs index` (legacy) is removed from the default flow; `cataforge kg ingest` is the canonical indexing path.
- `docs/.doc-index.json` is retained as a derived cache only; `cataforge kg export-index` regenerates it from KG.
- All tests pass with `store_backend = "oxigraph"` in CI (RocksDB path validated in CI, not just `memory`).
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
- Git status confirms no uncommitted partial-migration artefacts remain in `src/cataforge/kg/` that would affect the next migration attempt.

---

## §7.4 Technical Risk Register

| # | Risk | Probability | Impact | Mitigation | Detection Signal |
|---|------|-------------|--------|------------|-----------------|
| R-01 | **Data migration incompleteness**: entity extraction misses entities in non-standard section layouts (e.g., items nested inside HTML comment blocks, or in code fences within a section) | M | H | Use a two-pass extraction: first pass regex on stripped-code-block text, second pass over raw text with a stricter context filter; report unmatched known entity IDs (from `.doc-index.json` `items` field) as warnings | `kg_ingestion_completeness` gate below threshold; entity count in KG < entity count in `.doc-index.json` |
| R-02 | **KG library selection change / deprecation**: pyoxigraph primary author (@Tpt) abandons or significantly changes the API between 0.5.x and a future version, breaking the RocksDB store format | L | H | Pin `pyoxigraph>=0.5.8,<0.6` in `pyproject.toml`; maintain a `memory`-backend fallback for all queries; abstract the store behind `GraphRepository` so a backend swap is a single-file change | pyoxigraph GitHub repository shows archival or breaking-change release notes; wheel build failures on CI |
| R-03 | **Performance regression on large projects**: SPARQL queries over a large graph (thousands of entities) take longer than the legacy O(1) index lookup, degrading agent startup latency | M | M | Benchmark on a synthetic graph of 5,000+ triples before Beta exit; add SPARQL LIMIT clauses to all agent startup queries; maintain `.doc-index.json` as a derived cache for the most frequent O(1) lookups | Agent startup latency measurement in CI exceeds 2× baseline; `cataforge kg benchmark` report |
| R-04 | **Agent/skill call-layer semantic divergence**: migrated SPARQL queries return subtly different content than `loader.extract()` for edge cases (e.g., multi-volume documents, split sections) | M | H | Implement `cataforge kg compare-read` sampling (§7.5); run comparison on every doc type and split-volume variant before Beta exit; maintain legacy fallback path until comparison passes | `compare-read` alarm fires; doc-review AI layer detects inconsistencies between KG-loaded context and expected content |
| R-05 | **Third-party extension compatibility**: downstream projects using custom `cataforge` plugins or directly importing `docs/.doc-index.json` as a data source break after it becomes a derived cache | M | M | Document `.doc-index.json` as derived-only with one release's advance warning; provide `cataforge kg export-index` as a backward-compatible regeneration command; survey known external integrations before GA | External projects report import errors or missing fields in `.doc-index.json` |
| R-06 | **Dual-track consistency drift**: during Beta, KG and Markdown diverge because an agent writes to Markdown (via `doc-gen` skill) but the KG is not updated in the same transaction | H | M | Enforce KG-leading write: `doc-gen finalize` must call `cataforge kg ingest --doc-file` after every `cataforge docs index --doc-file`; make the two calls atomic via a single CLI wrapper; `cataforge kg reconcile` catches any drift that slips through | `cataforge kg reconcile` reports non-zero divergence; `compare-read` alarm |
| R-07 | **Team / user learning cost for SPARQL**: agent authors and framework contributors unfamiliar with SPARQL may write incorrect or inefficient queries, introducing bugs in the migrated call layer | H | M | Provide a `GraphRepository` Python abstraction hiding SPARQL for the most common access patterns (`find_by_id`, `find_outbound`, `trace_to_root`); document SPARQL patterns in `docs/reference/kg-query-patterns.md`; code-review checklist item for any new SPARQL query | Code review flags invalid SPARQL; `cataforge kg validate-queries` reports parse errors; agent integration tests fail |
| R-08 | **Traceability extraction false-positive / false-negative**: `XREF_RE` in the migration script matches references that are in code fences, comments, or deprecated sections, generating incorrect KG edges; or misses references in non-standard formats | M | H | Apply the same `_strip_code_blocks` logic used in `checker.py`, but extend it to handle fenced blocks with language tags and inline code; add a second filter for `<!-- deprecated -->` sections; measure precision/recall against a hand-labeled reference set before Beta exit | Traceability completeness metric shows unexpected edges; doc-review Layer 1 SPARQL checks report fewer or more covered entities than expected; human review of a sample KG export |

---

## §7.5 Dual-Track Running Plan (Beta Phase)

### Double-Write Strategy

During Beta, KG is the **source of truth**. Markdown files are derived snapshots. The write path is:

```
doc-gen finalize
  └─ Step 1: cataforge docs index --doc-file <path>   [legacy index update, retained for backward compat]
  └─ Step 2: cataforge kg ingest --doc-file <path>     [KG write — authoritative]
  └─ Step 3: cataforge kg export --doc-file <path>     [KG → Markdown re-export, overwrites file with canonical form]
```

Steps 1–3 are wrapped in a single `cataforge kg commit --doc-file <path>` command that executes them atomically (all succeed or all are rolled back). If Step 2 fails, Step 3 does not execute and Step 1 is reverted.

### Double-Read Comparison

`cataforge kg compare-read` is a sampling command that:

1. Takes a random sample of N references from `.doc-index.json` (default N = 20 per reconcile run, configurable).
2. For each reference, executes both:
   - Legacy: `loader.extract(ref, project_root)` → text string.
   - KG: SPARQL query for the entity section content → text string.
3. Computes Jaccard similarity on token sets of both results.
4. Reports any pair where similarity < threshold (default 0.95) as a divergence alarm.
5. Exits non-zero if any alarm fires; exits 0 if all samples are within threshold.

The comparison is run as part of `cataforge kg reconcile` and separately available as a standalone command for debugging.

### Consistency Check: `cataforge kg reconcile`

`cataforge kg reconcile` is a periodic task designed to detect and surface drift between KG and Markdown filesystem state. It runs in four steps:

1. **Scan**: enumerate all business docs in `docs/{doc_type}/`, extract all entity IDs and cross-references from Markdown source.
2. **Compare**: issue SPARQL queries to retrieve all entities and relations stored in KG.
3. **Diff**: compute the symmetric difference between Markdown-extracted entities/relations and KG-stored entities/relations. Any entity present in Markdown but absent in KG is a `missing` entry; any KG entity without a matching Markdown source is a `ghost` entry.
4. **Report**: write a structured diff report to `docs/.kg-reconcile-report.json`. Exit non-zero if any `missing` or `ghost` entries exist.

```pseudocode
function kg_reconcile(project_root, kg_store):
    md_entities = extract_all_entities_from_markdown(project_root)
    md_relations = extract_all_relations_from_markdown(project_root)

    kg_entities = sparql_select_all_entities(kg_store)
    kg_relations = sparql_select_all_relations(kg_store)

    missing_entities = md_entities - kg_entities
    ghost_entities   = kg_entities - md_entities
    missing_relations = md_relations - kg_relations
    ghost_relations   = kg_relations - md_relations

    report = {
        timestamp: utc_now(),
        missing_entities: list(missing_entities),
        ghost_entities:   list(ghost_entities),
        missing_relations: list(missing_relations),
        ghost_relations:   list(ghost_relations),
        divergence_count: len(missing_entities) + len(ghost_entities)
                        + len(missing_relations) + len(ghost_relations),
    }
    write_json(project_root / "docs/.kg-reconcile-report.json", report)

    if report.divergence_count > 0:
        exit(1)
    exit(0)
```

`kg reconcile` is intended to run:
- After every `cataforge kg commit --doc-file` (lightweight: only the updated doc's entities are compared).
- As a full-project sweep triggered by `cataforge doctor` or CI.

### Cutover Decision Points

**Stop double-write (KG-leading becomes sole write path; legacy `docs index` step removed):**

- `cataforge kg reconcile` reports zero divergence on all opted-in projects across 20 consecutive full-project sweeps.
- `cataforge kg compare-read` alarm has not fired in the last 10 sampling runs.
- No outstanding issues tagged `dual-track-regression` in the project tracker.

**Stop double-read (legacy `loader.extract()` path removed from all agent Input Contracts):**

- All 16 call sites in Task 1 §1.3 have been migrated to SPARQL-based access or are annotated `legacy-compat-permanent` with a documented rationale.
- `cataforge kg compare-read` has been decommissioned from `cataforge kg reconcile` (replaced by SHACL validation on every KG write).
- Phase 3 GA exit conditions are satisfied.

---

## [依赖传递摘要]

**关键决策:**
- 三阶段发布（Alpha/Beta/GA）均以可验证条件为门禁，Alpha 以 `kg_ingestion_completeness` gate 和 Markdown 导出往返无误为退出条件，Beta 以双读比对告警归零和所有 16 个调用点迁移完成为退出条件，GA 以 100% 项目切换 `coverage_mode=strict` 和遗留正则代码删除为退出条件。
- 数据迁移脚本采用六阶段管道（scan→parse→entity extraction→relation extraction→write→verify），幂等设计（IRI 由 entity ID 确定性派生，mtime 守卫跳过未变更实体），`coverage_mode=strict` 下只识别 `doc_id#§N.ITEM` 格式的跨文档引用。
- 双轨运行期 KG 主写（`kg commit` 原子三步），`kg reconcile` 检测漂移；两个切换决策点均以可验证条件（连续 N 次 reconcile 零漂移、compare-read 零告警）而非时间表为准。
- 风险寄存器 8 条，覆盖迁移完整性、库弃用、性能回退、语义漂移、第三方兼容、双轨一致性、学习成本、追溯提取假阳/假阴。

**输出物路径/位置:** `docs/proposals/kg-migration-0.5.0/task-7-rollout-strategy.md`

**阻塞标记:** NONE
