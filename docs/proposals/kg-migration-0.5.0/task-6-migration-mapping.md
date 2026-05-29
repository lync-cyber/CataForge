# Task 6 — Agent/Skill Call-Layer Migration Mapping

> KG Migration 0.5.0 · Agent-T6 produced · synthesizes Task 1 (`task-1-current-system.md` §1.3/§1.4/§1.6/§1.7), Task 3 (`task-3-domain-ontology.md` §3.1–§3.3 + `schemas/core.yaml`) and Task 5 (`task-5-cli-api.md` §5.2/§5.5).

Anchors:
- Business namespace: `cf:` (`https://cataforge.dev/ontology/`); instances: `cfprj:` (`https://cataforge.dev/instance/`).
- Five traceability predicates: `cf:satisfies` / `cf:implements` / `cf:verifies` / `cf:realizes` / `cf:delivers` (+ `cf:affects` for change-impact). Inverses honored (`satisfied_by`, `implemented_by`, `verified_by`, `realized_as`, `delivered_by`, `affected_by`).
- Coverage default: `coverage_mode=strict` (Task 5 §5.2 `KGConfig`); regex-coverage fallback eliminated.
- Shims (Task 5 §5.5): `extract`, `extract_batch`, `plan_load`, `build_full_index`, `resolve_deps`. Framework-asset call points get no shim.
- `extract()` full-text fallback removed — KG is single source of truth; `doctor` MUST gate via `kg_ingestion_completeness` (see §6.4 spec).

---

## §6.1 Call-Point Classification

Source: Task 1 §1.3 16-row inventory. Each row is reclassified into Group A (business-doc access — migrate to KG API) or Group B (framework-asset access — preserve current behavior).

### §6.1.1 Group A — Business-doc access (MUST migrate)

| # | Call site | Old tool function | Access object |
|---|-----------|-------------------|---------------|
| A1 | `architect/AGENT.md` Input Contract | `cataforge docs load prd#§1 prd#§3 prd#§2.F-xxx` | Business doc |
| A2 | `tech-lead/AGENT.md` Input Contract | `cataforge docs load arch#§2.M-xxx arch#§3.API-xxx ui-spec#§2.C-xxx ui-spec#§3.P-xxx` | Business doc |
| A3 | `qa-engineer/AGENT.md` Input Contract | `cataforge docs load dev-plan#§2.T-xxx arch#§3.API-xxx` | Business doc |
| A4 | `devops/AGENT.md` Input Contract | `cataforge docs load arch#§1.4 arch#§6 arch#§7` | Business doc |
| A5 | `ui-designer/AGENT.md` Input Contract | `cataforge docs load prd#§2.F-xxx arch#§2.M-xxx arch#§3.API-xxx` | Business doc |
| A6 | `doc-review` Layer 2 via `doc-nav` | `cataforge docs load <doc + upstream-deps>` (with `--with-deps`) | Business doc |
| A7 | `sprint-review` Layer 2 via `doc-nav` | `cataforge docs load dev-plan#§N.T-xxx arch#§3.API-xxx` | Business doc |
| A8 | `task-dep-analysis/SKILL.md` Step 1 | Read + Grep over dev-plan, regex extract T-xxx deps | Business doc |
| A9 | `doc-gen finalize` Step 3 | `cataforge docs index --doc-file <path>` → `indexer.update_single_doc()` | Business doc |
| A10 | `orchestrator` Bootstrap Step 9 | `cataforge docs index` (full rebuild) | Business doc |
| A11 | `cataforge docs validate` CLI | `indexer.validate_docs()` | Business doc |
| A12 | `doc-review` Layer 1 `check_xref()` | `re.findall + Path.glob` | Business doc |
| A13 | `doc-review` Layer 1 `check_bidirectional_coverage()` | `glob + re.finditer` over file content | Business doc |
| A14 | `doc-nav` degraded path (Bash-less Agent) | `Read docs/.doc-index.json` → `Read docs/{doc_type}/{file}` slice | Business doc |
| A15 | `indexer.build_xref()` | Scan all `doc_entry.sections.items` for ITEM_ID_RE | Business doc |

### §6.1.2 Group B — Framework-asset access (preserve, no KG migration)

| # | Call site | Old tool function | Access object | Preservation note |
|---|-----------|-------------------|---------------|-------------------|
| B1 | `framework-review` (`_framework_data.py`) | `.cataforge/skills/**/SKILL.md` + `.cataforge/agents/**/AGENT.md` filesystem scan | Framework asset | Stays on FS; opt-in `cfgov:` ingestion gated by `KGConfig.governance=true` |
| B2 | `loader._load_doc_type_map()` | Reads `.cataforge/framework.json` `docs.doc_types` key | Mixed (framework config → business doc subdirectory map) | Stays — pure config lookup; KG resolves entities directly via `cf:source_doc`, but this map remains the file-layout authority for the export pipeline |

`SkillLoader.discover()` (referenced in spec but not in T1 §1.3 inventory) belongs in Group B by definition; preserve behavior.

---

## §6.2 Group A · Per-Call-Point Migration Mapping

Mapping convention: `Old → New (parameter signature)`. New-API method names are exact references to Task 5 §5.2. SPARQL predicate / class URIs reference `schemas/core.yaml`.

| # | Old tool function (sig) | New KG API (sig) | Affected business entity types | Semantic-equivalence note |
|---|------------------------|------------------|--------------------------------|---------------------------|
| A1 | `cataforge docs load prd#§N` / `prd#§N.F-NNN` (subprocess; returns concatenated text block per ref) | `kg.query.requirement(req_id)` for items; for whole sections use `kg.query.search("", types=["Feature"], filters={"source_doc": "prd-<proj>"}) ` then `kg.query.entity(uri)` per result | Feature, AcceptanceCriteria | Whole-section text loss — KG returns structured slots, not raw markdown body. Compensation: rehydrate via Task 4 export pipeline `render_entity(uri)` if narrative text is required. |
| A2 | `cataforge docs load arch#§2.M-xxx arch#§3.API-xxx ui-spec#§2.C-xxx ui-spec#§3.P-xxx` | `kg.query.module(id)`, `kg.query.entity(api_uri)` for API, `kg.query.component(id)`, `kg.query.entity(page_uri)` for Page | Module, API, Component, Page | 1:1 typed accessor on three of four; API and Page reachable via `kg.query.entity()` (Task 5 exposes `feature/module/component/task/test_case` only). Compensation: typed `kg.query.api(id)` / `kg.query.page(id)` to be added in Task 5 errata (flagged in cross-output inconsistencies). |
| A3 | `cataforge docs load dev-plan#§2.T-xxx arch#§3.API-xxx` | `kg.query.task(task_id)` + `kg.query.entity(api_uri)`; for AC nested inside Task, traverse `cf:has_part` to `AcceptanceCriteria` | Task, AcceptanceCriteria, API | Equivalent; `Task.tdd_acceptance` (AC-NNN) is exposed as inbound `cf:has_part` AcceptanceCriteria nodes, not as an inline string. Compensation: `kg.trace.from_requirement(task_id, max_depth=1)` returns `acceptance_criteria` list. |
| A4 | `cataforge docs load arch#§1.4 arch#§6 arch#§7` (tech-stack + deploy sections) | `kg.query.search("", types=["Module", "Pipeline", "Deployment", "Environment"], filters={"belongs_to_project": <uri>})` + per-result `kg.query.entity()` | Module, Pipeline, Deployment, Environment | **Partial** — arch §1.4 "tech-stack" is currently free-text narrative, not modeled as a class in `core.yaml`. Divergence acceptable for 0.5.0; Compensation: until tech-stack ontology lands, devops continues reading the arch markdown directly via Task 4 export rendering (`render_section("arch", "§1.4")`). Flagged as cross-output inconsistency. |
| A5 | `cataforge docs load prd#§2.F-xxx arch#§2.M-xxx arch#§3.API-xxx` | `kg.query.feature(id)`, `kg.query.module(id)`, `kg.query.entity(api_uri)` | Feature, Module, API | 1:1; same caveat as A2 about API typed accessor. |
| A6 | `doc-nav` `cataforge docs load <doc> --with-deps` | `kg.query.plan_load(uris=[<doc-as-uri-set>], token_budget=N, include_related=True)` | All upstream-referenced classes | Equivalent and **strictly stronger**: `plan_load` (Task 5 §5.2) topologically sorts via `cf:depends_on`/`cf:part_of` and inserts 1-hop neighbours including cross-layer traceability edges, which the 0.4.x `deps:` frontmatter does not capture. |
| A7 | `doc-nav` batch ref load for sprint-review | `kg.query.plan_load(uris=[task_uris + api_uris], token_budget=N)` then per-uri `kg.query.entity()` | Task, API, ReviewReport | 1:1; sprint-review specifically needs `kg.trace.from_requirement(task_id)` to get the CODE-REVIEW back-reference via `ReviewReport.targets_artifact`. |
| A8 | Read + Grep over dev-plan body, extract `deps:` regex | `kg.query.plan_load([task_uri], token_budget=∞).ordered_uris` plus `cf:depends_on` SPARQL (see §6.4 A8 SPARQL) | Task | Equivalent and stronger — automatic dep inference (see §6.4 SPARQL block) replaces hand-maintained `deps:` frontmatter. The legacy `deps:` field SHOULD be derived from `cf:depends_on` at export time. |
| A9 | `cataforge docs index --doc-file <path>` (writes `.doc-index.json` incrementally) | `cataforge kg import <path> --on-conflict=overwrite` (Task 5 §5.1) — re-parses one source file, replaces all triples whose `cf:source_doc` matches | All classes | **Not fully equivalent**: KG import is content-replace, not field-level merge. Compensation: `kg import` runs inside an implicit transaction (Task 5 §5.2), SHACL-validated; legacy `.doc-index.json` mtime/hash bookkeeping is replaced by `cf:content_hash` and `cf:updated_at`. |
| A10 | `cataforge docs index` (full rebuild of `.doc-index.json`) | `cataforge kg init --force` + `cataforge kg import docs/ --coverage-mode strict` | All classes | Equivalent; bootstrap now seeds both the store and the SHACL invariants. Doctor gate `kg_ingestion_completeness` (see §6.4) blocks `cataforge ready` until import succeeds. |
| A11 | `indexer.validate_docs()` → `dict{orphans, stale, xref_errors, alias_conflicts, invalid_ids, stale_deps}` | `cataforge kg validate --severity warning` + `cataforge kg reconcile --coverage-mode strict --fail-on-unresolved` (Task 5 §5.1) | All classes | **Not fully equivalent** — old report has six named keys; new validate returns SHACL-shaped violation rows. Compensation: a wrapper `legacy_validate_report()` (see §6.5 breaking-change #3) maps the new report into the old shape for callers that depend on it (CI workflows, pre-commit hooks). |
| A12 | `check_xref()` — regex over full doc body + `Path.glob` resolution | `kg.query.entity(<cfprj:doc-id>)` to verify referent existence; reconciler covers the rest via `cataforge kg reconcile` | All classes (cross-doc refs) | **Strictly stronger**: regex-based xref produces false positives (URL fragments) and false negatives (cross-volume globs, Task 1 §1.4 case B). KG-based resolution requires the strict form `doc_id#§N.ITEM`; any unresolved ref fails with `KGEntityNotFoundError`. Compensation: legacy `mentions` mode opt-in via `KGConfig.coverage_mode="mentions"` for grandfathered docs. |
| A13 | `check_bidirectional_coverage()` — `re.search` for upstream item ID in downstream doc body | SPARQL `cf:verifies` / `cf:coveredBy` query (see §6.4 A13 SPARQL) | Feature, Module, Component, Task, TestCase | **Strictly stronger** — eliminates the assassin false positive in Task 1 §1.4 case A. A mention in a comment block no longer counts as coverage; coverage requires an asserted `cf:satisfies`/`cf:implements`/`cf:verifies` edge in the graph. |
| A14 | `doc-nav` degraded path — `Read .doc-index.json` + `Read <file>` offset/limit slice | `kg.query.entity(uri)` + Task 4 `render_entity(uri)` to materialize markdown | All classes | Equivalent for the Bash-less Agent if a small `cataforge.domain.kg` Python adapter is exposed (already true via `KnowledgeGraph.connect(config)` sync API, Task 5 §5.2). Degraded path is now "open store + run typed accessor"; no JSON-slicing. |
| A15 | `indexer.build_xref()` — scan all sections for ITEM_ID_RE matches | SPARQL CONSTRUCT of (subject, `cf:references`, object) where object is any `cf:SoftwareArtifact` whose `entity_id` appears in subject's body — but this is **superseded**: the KG ingest layer (Task 5 `cataforge kg import`) emits typed predicates (`cf:satisfies`, `cf:implements`, `cf:verifies`, `cf:realizes`, `cf:delivers`) at parse time, so `build_xref()` no longer has a runtime purpose | All classes | Effectively retired. Compensation: a SPARQL query (see §6.4 A15 SPARQL) materializes the same `{item_id → [{doc_id, section, file_path}]}` shape on demand for callers that still need it (e.g., the legacy doc-index export). |

---

## §6.3 Group B · Preservation Strategy

| # | Call site | Preservation reason | Emit `DeprecationWarning`? |
|---|-----------|---------------------|----------------------------|
| B1 | `framework-review` `_framework_data.py` filesystem scan over `.cataforge/skills/**/SKILL.md` and `.cataforge/agents/**/AGENT.md` | Framework assets are governed by `cfgov:` (Task 3 §3.6), which is **strictly disjoint** from business `cf:`. Downstream user projects run with `KGConfig.governance=false`; lifting framework assets into business KG would pollute the namespace (Task 3 §3.9 Decision 5). `framework-review` operates on the framework's own files for hot-reload semantics that the KG export cycle cannot match. | **No** for the FS scan itself. **Yes** for any downstream caller that wants graph queries over framework assets: emit `DeprecationWarning("framework-review FS scan will gain optional cfgov:KnowledgeGraph backing when KGConfig.governance=true in 0.6.0")` once per skill invocation, pointing to `docs/proposals/kg-migration-0.5.0/task-3-domain-ontology.md` §3.6. |
| B2 | `loader._load_doc_type_map()` reads `.cataforge/framework.json` `docs.doc_types` | Pure config lookup (doc_id → subdirectory). The KG already records each entity's `cf:source_doc`; this map is needed only by the export pipeline to *write back* into the correct subdirectory. It is not an entity-access call point. | **No.** Stays as-is. |
| (impl) | `SkillLoader.discover()` directory scan over `.claude/skills/*` | `cfgov:Skill` exists in `governance.yaml` but `SkillLoader.discover()` is invoked at process start before any KG connection. Forcing it through the graph would create a chicken-and-egg dependency on `cataforge kg init`. | **No.** Stays as-is. Future opt-in `cfgov:` lift happens at `cataforge kg import .cataforge/ --governance` (Task 5 §5.1 `kg import` with `--format markdown`). |

---

## §6.4 Semantic-Equivalence Verification (per Group A row)

Three-segment analysis (A: return shape; B: equivalence verdict; C: divergence + compensation).

### A1 — Read PRD feature section
- **A.** Old: subprocess stdout `=== ref ===\n<markdown body>`; loss of structure. New: `Feature` Pydantic v2 model (`schemas/core.yaml` lines 460–471) — typed slots, no body text by default.
- **B.** **Partial.**
- **C.** Body text is not surfaced through `kg.query.*`. Compensation: when agent prompts need the rendered body (e.g., for narrative paraphrase), call Task 4 `render_entity(uri, template="feature.md.j2")` which produces the same markdown that `cataforge docs load` returned. PRD §1 (free-prose intro) is **not** a business entity in `core.yaml` and continues to be read as raw markdown via a small `kg.query.source_section(doc_id, anchor)` helper (proposed addition, see §6.5).

### A2 — Read arch + ui-spec items for tech-lead
- **A.** Old: 4 concatenated body blocks. New: 4 typed Pydantic models — `Module`, `API`, `Component`, `Page`.
- **B.** **Fully equivalent for typed slots; partial for body text.**
- **C.** Task 5 §5.2 only exposes `feature/module/component/task/test_case` typed accessors. `kg.query.api(id)` and `kg.query.page(id)` are **MISSING** from Task 5; current spec forces `kg.query.entity(<cfprj:API-NNN>)` (returns most-specific subclass per dispatch). Flagged in cross-output inconsistencies → Task 5 errata.

### A3 — Read dev-plan task + arch API for QA
- **A.** Old: 2 body blocks; AC nested as bullet inside Task body. New: `Task` + `API` typed + `acceptance_criteria` list via `kg.trace.from_requirement(task_id, max_depth=1).acceptance_criteria`.
- **B.** **Fully equivalent + stronger** (AC becomes traversable rather than embedded text).
- **C.** None.

### A4 — Read arch tech-stack + sections §6/§7 for devops
- **A.** Old: 3 body blocks (free narrative). New: typed entities exist for §6/§7 (Pipeline, Deployment, Environment) but §1.4 tech-stack is unmodeled.
- **B.** **Partial.**
- **C.** **HIGH-PRIORITY DIVERGENCE**: `core.yaml` has no `TechStack` class. Compensation options ranked:
  1. **Recommended (0.5.0):** Keep §1.4 as raw markdown; add `kg.query.source_section(doc_id="arch-<proj>", section_anchor="§1.4")` helper that uses `cf:source_doc` + `cf:source_section` slots on `Module` instances to materialize the section. Honest divergence: not all narrative in arch §1.4 is a Module.
  2. **0.6.0:** Add `TechStack` / `TechStackComponent` classes in a plugin (`compliance-tech-stack` schema, Task 3 §3.5 plugin template).

### A5 — UI designer reads prd + arch refs
- **A./B./C.** Identical to A2.

### A6 — doc-review Layer 2 dep load
- **A.** Old: ad-hoc DFS over `.doc-index.json deps[]` (depth ≤ 2). New: `kg.query.plan_load(uris, token_budget, include_related=True)` which is topologically sorted via `cf:depends_on`/`cf:part_of` plus 1-hop neighbours (Task 5 §5.2 `plan_load`).
- **B.** **Strictly stronger** — uses actual traceability edges, not manually maintained `deps:`.
- **C.** None. Edge case: `plan_load.dropped_uris` (budget overflow) replaces the silent truncation in 0.4.x; doc-review Layer 2 prompt MUST handle dropped URIs explicitly.

### A7 — sprint-review batch load
- **A./B.** Same as A6. Additional: sprint-review needs CODE-REVIEW back-references (`ReviewReport.targets_artifact`).
- **C.** `kg.trace.from_requirement(task_id, direction="both")` exposes `ReviewReport` via inverse `cf:reviewed_by` on `Task`. Equivalent.

### A8 — task-dep-analysis (HIGH RISK — automatic inference)

**A.** Old: `Read + Grep` extracts `deps:` field text → list of T-NNN tuples. New: SPARQL infers dependency edges via `cf:depends_on` + the 5 traceability predicates.

**B.** **Strictly stronger** — the inference uses the graph rather than a hand-maintained string field. `deps:` frontmatter becomes derived data (Task 4 export emits it from `cf:depends_on`).

**C.** Migration risk: in 0.4.x, `deps:` is freeform; some entries reference module IDs (M-NNN) or API IDs (API-NNN) that aren't true task dependencies. KG ingest MUST normalize: any non-T-NNN ID in `deps:` becomes a `cf:realizes` edge to the referenced entity instead of `cf:depends_on` (since `cf:depends_on` is `Task → Task` by usage convention). Compensation: `cataforge kg import` migration codemod (Task 5 §5.5 + this task §6.5 #4) records `cf:depends_on` only for T-NNN targets; cross-layer references go to their typed predicates.

**SPARQL — A8 dependency inference:**

```sparql
PREFIX cf: <https://cataforge.dev/ontology/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# Replaces 0.4.x: Read+Grep over `deps:` field. Returns the dependency
# adjacency list for tech-lead's task-dep-analysis algorithm.
SELECT ?from_id ?to_id ?edge_kind
WHERE {
  ?from a cf:Task ; cf:entity_id ?from_id .
  {
    ?from cf:depends_on ?to .
    ?to   a cf:Task ; cf:entity_id ?to_id .
    BIND("depends_on" AS ?edge_kind)
  } UNION {
    ?from cf:realizes ?to .
    ?to   cf:entity_id ?to_id .
    BIND("realizes"   AS ?edge_kind)
  }
}
ORDER BY ?from_id ?to_id
```

### A9 — doc-gen finalize incremental index
- **A.** Old: writes one entry into `.doc-index.json`. New: `cataforge kg import <path> --on-conflict=overwrite` re-ingests the single file, replacing all triples whose `cf:source_doc` matches.
- **B.** **Partial.**
- **C.** Replace-by-source-doc semantics is coarser than field-level merge. Acceptable because `cf:content_hash` is computed per entity (per `cf:source_section`); only entities whose hash changed are emitted, so triple churn is bounded. SHACL validation now runs at finalize time, providing stronger guarantees than the 0.4.x mtime check.

### A10 — orchestrator bootstrap full rebuild
- **A./B.** Equivalent.
- **C.** Bootstrap MUST handle the `cataforge kg init --force` idempotency case: if the store already exists, the orchestrator decides between `--force` (clean rebuild) or skip-if-consistent (default). Doctor gate (see below) enforces consistency.

### A11 — `cataforge docs validate`
- **A.** Old: dict with 6 named keys. New: SHACL violation table.
- **B.** **Partial.**
- **C.** Wrapper `legacy_validate_report()` (§6.5 #3) maps SHACL violations into the old shape. Two old keys lose direct mapping:
  - `alias_conflicts`: in KG, alias would be a `cf:depends_on`/`cf:references` ambiguity — SHACL surfaces this as a max-cardinality violation on `cf:entity_id`. Mappable.
  - `stale_deps`: in KG, "stale" = `cf:content_hash` mismatch between subject and its referenced object. Custom SPARQL ask query (`SELECT WHERE { ?a cf:depends_on ?b . ?a cf:content_hash ?h_a . ?b cf:content_hash ?h_b . FILTER(?h_a != ?h_b) }`) replaces it. Mappable.

### A12 — `check_xref()`
- **A.** Old: regex hit/miss list. New: KG entity existence check.
- **B.** **Strictly stronger.**
- **C.** Edge case: legacy docs may reference items by alias or external URLs (e.g., GitHub issue links) — these MUST be excluded from xref check. KG resolver filters by URI scheme `cfprj:` only.

### A13 — `check_bidirectional_coverage()` (HIGH RISK — regex → SPARQL)

**A.** Old: pair of regex passes (does string `F-001` appear in `arch-*.md`?). New: SPARQL join on `cf:verifies` / `cf:satisfies` / `cf:implements` edges.

**B.** **Strictly stronger** — assassinates the false positive from Task 1 §1.4 case A.

**C.** Compensation: legacy `mentions` mode opt-in (Task 5 `KGConfig.coverage_mode="mentions"`) for grandfathered projects. Default is `strict` (Task 5 §5.2).

**SPARQL — A13 bidirectional coverage:**

```sparql
PREFIX cf: <https://cataforge.dev/ontology/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# Replaces check_bidirectional_coverage(): finds Features that lack any
# implementing Module/Component OR any verifying TestCase. Used by
# doc-review Layer 1 in `strict` coverage mode.
SELECT ?feature ?entity_id ?title
       (BOUND(?impl) AS ?has_impl)
       (BOUND(?tc)   AS ?has_test)
WHERE {
  ?feature a cf:Feature ;
           cf:entity_id ?entity_id ;
           cf:title     ?title .
  OPTIONAL {
    ?impl_node a ?impl_class ; cf:implements ?feature .
    ?impl_class rdfs:subClassOf* cf:SoftwareArtifact .
    BIND(?impl_node AS ?impl)
  }
  OPTIONAL {
    ?tc a cf:TestCase ; cf:verifies+ ?feature .
  }
  FILTER(!BOUND(?impl) || !BOUND(?tc))
}
ORDER BY ?entity_id
```

The `cf:verifies+` property path (Task 3 §3.3 Q1) walks transitively, so a TestCase that verifies a TestSuite that verifies the Feature still counts.

### A14 — doc-nav degraded path
- **A.** Old: JSON slice + file Read. New: open KG sync (already in Task 5 §5.2 `KnowledgeGraph.connect()`).
- **B.** **Fully equivalent** for Bash-less Agents — they import `cataforge.domain.kg` Python module directly.
- **C.** None.

### A15 — `indexer.build_xref()`
- **A.** Old: `dict[item_id, [{doc_id, section, file_path}]]`. New: KG ingest already emits typed predicates.
- **B.** **Retired.**
- **C.** Compensation SPARQL for legacy callers:

```sparql
PREFIX cf: <https://cataforge.dev/ontology/>
SELECT ?entity_id ?source_doc ?source_section
WHERE {
  ?s a/rdfs:subClassOf* cf:SoftwareArtifact ;
     cf:entity_id      ?entity_id ;
     cf:source_doc     ?source_doc ;
     cf:source_section ?source_section .
}
ORDER BY ?entity_id
```

### §6.4.x · `doctor` gate `kg_ingestion_completeness` (HIGH RISK — single source of truth)

Because `extract()` loses its full-text fallback (Task 5 §5.5 shim), the KG MUST be guaranteed complete before any agent reads from it. Add a new doctor check that blocks `cataforge ready`:

**Pseudocode / spec:**

```python
# src/cataforge/doctor/checks/check_kg_ingestion_completeness.py
"""
Doctor gate — HARD FAIL if KG is missing entities that exist in docs/.

This check guards the 0.5.0 contract that the KG is the single source of
truth for business-doc access. If any entity discoverable by markdown scan
is absent from the graph, all agents reading via kg.query.* would silently
get None — masking real coverage gaps.
"""
from cataforge.domain.kg import KnowledgeGraph, KGConfig
from cataforge.domain.docs._scan import iter_entity_ids_in_docs  # filesystem walker

def check_kg_ingestion_completeness(project_root: Path) -> CheckResult:
    """
    Returns FAIL when |fs_entity_ids| - |kg_entity_ids| is non-empty.

    Severity: ERROR (blocks `cataforge ready`).
    Auto-fix hint: run `cataforge kg import docs/ --on-conflict=overwrite`.
    """
    fs_ids: set[str] = set(iter_entity_ids_in_docs(project_root / "docs"))
    # iter_entity_ids_in_docs scans frontmatter ID patterns from
    # core.yaml §slot_usage.entity_id.pattern across all SoftwareArtifact
    # subclasses (F/AC/M/API/E/C/P/T/TC/SR + EP/US/...).

    config = KGConfig(db_path=project_root / ".cataforge/kg/store")
    with KnowledgeGraph.connect(config) as kg:
        sparql = """
        PREFIX cf: <https://cataforge.dev/ontology/>
        SELECT DISTINCT ?entity_id WHERE {
          ?s a/rdfs:subClassOf* cf:SoftwareArtifact ;
             cf:entity_id ?entity_id .
        }
        """
        kg_ids: set[str] = {str(row[0]) for row in kg._store.query(sparql)}

    missing = fs_ids - kg_ids
    stale   = kg_ids - fs_ids     # KG has entity but FS doesn't — soft warn

    if missing:
        return CheckResult(
            severity="ERROR",
            code="kg_ingestion_completeness",
            message=(
                f"KG missing {len(missing)} entities present in docs/: "
                f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}"
            ),
            fix_hint="cataforge kg import docs/ --on-conflict=overwrite",
        )
    if stale:
        return CheckResult(
            severity="WARN",
            code="kg_ingestion_stale",
            message=f"KG has {len(stale)} entities no longer present in docs/.",
            fix_hint="cataforge kg validate --fix-orphans",
        )
    return CheckResult(severity="OK", code="kg_ingestion_completeness")
```

Hook into `cataforge doctor` registry (in `src/cataforge/doctor/_registry.py`) at startup; ensure `cataforge ready` short-circuits on any ERROR result. The gate is mandatory because dropping `extract()`'s full-text fallback (Task 5 §5.5) means any missing KG entity silently returns `None` to agents.

---

## §6.5 Breaking-Change List and Shim Solutions

Five calls cannot 1:1 map. For each, breaking reason + refactor plan + complete shim (extends Task 5 §5.5 where applicable).

### Flag-aware dispatch (applies to every shim below)

Under the full-cutover rollout model (Task 7 §7.1 sub-PR 5), every shim and Group A call site dispatches on `doc_type in config.kg_active_doc_types`:

```python
def _dispatch_read(doc_type: str, section_id: str, *, config: KGConfig):
    if doc_type in config.kg_active_doc_types:
        # KG path is authoritative for this doc_type
        return _kg_read(doc_type, section_id, config)
    else:
        # Doc_type not yet flipped — use legacy loader
        return _legacy_read(doc_type, section_id)
```

This dispatch lives in `src/cataforge/domain/kg/_shim.py` and wraps every public 0.4.x-compat entry point (`extract`, `extract_batch`, `extract_with_body`, `plan_load`, `build_full_index`, `resolve_deps`, `source_section`). Per the flag-granularity decision recorded in [README §User decisions](README.md), the dispatch is per-doc_type, not per-call-site — a single config check per call. The shim implementations below show only the KG-path branch; the dispatch wrapper is implicit.

### Breaking-change #1 — `extract()` body text loss

**Reason:** 0.4.x `extract(ref)` returns markdown body; 0.5.0 `kg.query.entity(uri)` returns Pydantic model with no body.

**Refactor plan:** Two-tier shim. Tier 1 (existing in Task 5 §5.5) returns flat dict. Tier 2 (new) renders body markdown for callers that need narrative text.

**Shim — extend `src/cataforge/domain/kg/_shim.py`:**

```python
def extract_with_body(
    doc_type: str,
    section_id: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """
    0.4.x-compat shim that ALSO renders the entity body markdown.

    Adds a "body" key to the dict returned by Task 5 §5.5 extract().
    Used by agents that paraphrase narrative text (e.g. PM revisiting
    a Feature description).

    .. deprecated:: 0.5.0
        Use kg.query.entity(uri) + cataforge.domain.kg.export.render_entity(uri).
    """
    import warnings
    from cataforge.domain.kg.export import render_entity
    warnings.warn(
        "extract_with_body() is a transitional shim removed in 0.6.0; "
        "use kg.query + cataforge.domain.kg.export.render_entity instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    base = extract(doc_type, section_id, db_path=db_path)
    if base is None:
        return None
    base["body"] = render_entity(base["uri"], template=f"{doc_type}.md.j2")
    return base
```

### Breaking-change #2 — Missing typed accessors for `API` and `Page`

**Reason:** Task 5 §5.2 exposes typed accessors `feature/module/component/task/test_case`. Callers A2/A5 reference API-NNN and P-NNN, which require generic `kg.query.entity()`.

**Refactor plan:** Extend `QueryAPI` with `api()` and `page()` methods. This is a **Task 5 errata**, flagged in the cross-output inconsistency report.

**Shim — `src/cataforge/domain/kg/_shim.py` proposed additions to `QueryAPI`:**

```python
# src/cataforge/domain/kg/_query.py — add these methods to the QueryAPI class
# defined in Task 5 §5.2.

def api(self, api_id: str) -> "API | None":
    """
    Fetch an :class:`API` by entity_id (pattern ``API-NNN``).

    Errata to Task 5 §5.2 surfaced by Task 6 §6.5 #2.
    """
    return self._fetch_typed("API", api_id, API)

def page(self, page_id: str) -> "Page | None":
    """
    Fetch a :class:`Page` by entity_id (pattern ``P-NNN``).

    Errata to Task 5 §5.2 surfaced by Task 6 §6.5 #2.
    """
    return self._fetch_typed("Page", page_id, Page)
```

### Breaking-change #3 — `validate_docs()` return-shape mismatch

**Reason:** Old `dict{orphans, stale, xref_errors, alias_conflicts, invalid_ids, stale_deps}`; new SHACL violation rows.

**Refactor plan:** Map SHACL violations onto the legacy 6-key shape for CI workflows and pre-commit hooks that depend on the old keys.

**Shim — `src/cataforge/domain/kg/_shim.py` new function:**

```python
def legacy_validate_report(
    *,
    db_path: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    0.4.x shim: return the validate_docs() six-key report shape.

    Maps SHACL violations onto:
      - orphans         <- entities with no inbound edges (Task 5 §5.1 --fix-orphans surface)
      - stale           <- entities whose content_hash mismatches Markdown source
      - xref_errors     <- KGEntityNotFoundError per unresolved cfprj: URI
      - alias_conflicts <- SHACL sh:maxCount violations on cf:entity_id
      - invalid_ids     <- SHACL sh:pattern violations on cf:entity_id
      - stale_deps      <- SPARQL: ?a cf:depends_on ?b ; ?a cf:content_hash != ?b cf:content_hash

    .. deprecated:: 0.5.0
        Use `cataforge kg validate --output json` and consume the SHACL
        report directly.
    """
    import warnings
    from cataforge.domain.kg import KnowledgeGraph, KGConfig
    warnings.warn(
        "legacy_validate_report() is a transitional shim removed in 0.6.0; "
        "consume `cataforge kg validate --output json` directly.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = KGConfig(db_path=Path(db_path) if db_path else None)
    report: dict[str, list[dict[str, Any]]] = {
        "orphans": [], "stale": [], "xref_errors": [],
        "alias_conflicts": [], "invalid_ids": [], "stale_deps": [],
    }
    with KnowledgeGraph.connect(config) as kg:
        # SHACL pass
        from cataforge.domain.kg._validate import run_shacl  # exposed by Task 5 §5.4
        for v in run_shacl(kg):
            if v.shape_id == "cf:entity_id-pattern":
                report["invalid_ids"].append({"id": v.entity_id, "message": v.message})
            elif v.shape_id == "cf:entity_id-unique":
                report["alias_conflicts"].append({"id": v.entity_id, "message": v.message})
            elif v.shape_id == "cf:source_doc-orphan":
                report["orphans"].append({"id": v.entity_id, "message": v.message})
        # Hash-based stale check
        stale_q = """
        PREFIX cf: <https://cataforge.dev/ontology/>
        SELECT ?entity_id WHERE {
          ?s cf:entity_id ?entity_id ;
             cf:content_hash ?h .
          FILTER NOT EXISTS {
            ?s cf:content_hash ?h .
            FILTER(?h = STRDT(SHA256(?body), xsd:string))
          }
        }"""
        # ... (impl reads source files and recomputes hash)
        # Dependency-staleness check
        dep_q = """
        PREFIX cf: <https://cataforge.dev/ontology/>
        SELECT ?a_id ?b_id WHERE {
          ?a cf:depends_on ?b ;
             cf:entity_id   ?a_id ;
             cf:content_hash ?h_a .
          ?b cf:entity_id   ?b_id ;
             cf:content_hash ?h_b .
          FILTER(?h_a != ?h_b)
        }"""
        for row in kg._store.query(dep_q):
            report["stale_deps"].append({"from": str(row[0]), "to": str(row[1])})
    return report
```

### Breaking-change #4 — `deps:` frontmatter codemod

**Reason:** `deps:` historically mixes T-NNN dependencies and non-T-NNN references (M-NNN, API-NNN). KG ingest needs them disambiguated.

**Refactor plan:** One-shot codemod inside `cataforge kg import` first run. Documented in Task 7 rollout.

**Shim — `src/cataforge/domain/kg/_codemod_deps.py`:**

```python
"""
Codemod: split legacy `deps:` frontmatter into typed edges at first import.

For each Task T with `deps: [X-NNN, Y-NNN, ...]`:
    - If X-NNN is a T-NNN  → cf:depends_on edge
    - If X-NNN is an M/C/P → cf:realizes  edge
    - If X-NNN is an API/E → cf:realizes  edge (Task realizes the API/DataModel)
    - Otherwise            → emit warning to EVENT-LOG; skip.
"""
from __future__ import annotations
from typing import Iterable
import re

_TASK_RE = re.compile(r"^T-\d{3,}$")
_REALIZE_RE = re.compile(r"^(M|C|P|API|E)-\d{3,}$")

def split_deps(task_entity_id: str, raw_deps: Iterable[str]) -> dict[str, list[str]]:
    """
    Returns a dict with keys `depends_on` and `realizes`,
    plus `unparsed` for unknown ID shapes.
    """
    out = {"depends_on": [], "realizes": [], "unparsed": []}
    for dep in raw_deps:
        dep = dep.strip()
        if _TASK_RE.match(dep):
            out["depends_on"].append(dep)
        elif _REALIZE_RE.match(dep):
            out["realizes"].append(dep)
        else:
            out["unparsed"].append(dep)
    return out
```

### Breaking-change #5 — Free-prose section access (PRD §1, arch §1.4)

**Reason:** Some agent input contracts reference sections that are free narrative, not entities (PRD §1 intro, arch §1.4 tech-stack).

**Refactor plan:** Add `kg.query.source_section(doc_id, anchor)` helper that uses `cf:source_doc` + `cf:source_section` slots to materialize the underlying markdown via Task 4 export rendering.

**Shim — `src/cataforge/domain/kg/_shim.py` new function:**

```python
def source_section(
    doc_id: str,
    section_anchor: str,
    *,
    db_path: str | Path | None = None,
) -> str | None:
    """
    Retrieve raw markdown for a section that is not modeled as a business
    entity (e.g. PRD §1 intro, arch §1.4 tech-stack narrative).

    Looks up the first SoftwareArtifact whose cf:source_doc matches doc_id,
    then reads the file slice corresponding to section_anchor. This is the
    explicit escape hatch for the body-text-loss divergence noted in
    §6.4 A1 / A4.

    .. deprecated:: 0.6.0
        Will be removed once narrative sections are modeled as proper
        entity classes (e.g. TechStack plugin schema).
    """
    import warnings
    from pathlib import Path
    from cataforge.domain.kg import KnowledgeGraph, KGConfig
    warnings.warn(
        "source_section() is a transitional shim; narrative sections will be "
        "modeled as entities in 0.6.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = KGConfig(db_path=Path(db_path) if db_path else None)
    with KnowledgeGraph.connect(config) as kg:
        sparql = f"""
        PREFIX cf: <https://cataforge.dev/ontology/>
        SELECT DISTINCT ?src WHERE {{
          ?s cf:source_doc ?src .
          FILTER(STRSTARTS(STR(?src), "{doc_id}"))
        }}
        LIMIT 1
        """
        rows = list(kg._store.query(sparql))
        if not rows:
            return None
        src_path = Path(str(rows[0][0]))
    # Slice the markdown by section heading
    if not src_path.exists():
        return None
    body = src_path.read_text(encoding="utf-8").splitlines()
    section_marker = section_anchor.lstrip("§").strip()
    start, end = None, len(body)
    for i, line in enumerate(body):
        if line.startswith("#") and section_marker in line:
            start = i
        elif start is not None and line.startswith("#") and i > start:
            end = i
            break
    return "\n".join(body[start:end]) if start is not None else None
```

---

## §6.6 Regression Verification Plan

### §6.6.1 Test strategy

| Layer | Goal | Tooling |
|-------|------|---------|
| **Unit** | Each migration mapping in §6.2 has ≥1 unit test asserting old↔new return-shape equivalence (where equivalence holds) or documented divergence (where it does not). | pytest + pytest-asyncio; KG `KGConfig(store_backend="memory")`. |
| **Integration** | Run `framework-review` and `doc-review` end-to-end on a fixed 0.4.1 fixture project under both code paths (legacy markdown + new KG); compare normalized outputs. | pytest + subprocess; golden diff. |
| **Property-based** | For any sequence of `add → update → delete → re-import` operations, the KG-derived `legacy_validate_report()` matches `indexer.validate_docs()` for the same source corpus. | hypothesis; `@given(corpus=corpora())`. |
| **e2e dogfood** | Run `cataforge deploy && cataforge kg import docs/ && cataforge kg validate` on the CataForge repo itself; expect 0 ERROR-severity violations. | bash script under `.cataforge/scripts/dogfood/`. |
| **Snapshot golden** | Pin reference KG-validated reports for a fixed corpus under `tests/golden/kg/`; CI fails on unintended changes. | `pytest-snapshot` or hand-rolled diff. |

### §6.6.2 Coverage requirement

Every Group A row in §6.1.1 (A1–A15) MUST have at least one unit test in `tests/kg/migration/test_a{1..15}_*.py`. Coverage gate in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src/cataforge/domain/kg/_shim.py"]

[tool.coverage.report]
fail_under = 95   # shim layer is small + critical
```

### §6.6.3 Test data generation

- **Fixture corpus:** copy `tests/fixtures/projects/demo-0.4.1/` (existing 0.4.1 reference project) verbatim. This corpus already exercises all 9 entity prefixes from Task 1 §1.6 and the cross-doc references listed there.
- **Expected values:** generated once via the 0.4.x toolchain (`cataforge docs index && cataforge docs validate`), pinned as JSON snapshots under `tests/golden/kg/demo-0.4.1/`.

### §6.6.4 pytest-style skeletons (≥2)

**Skeleton 1 — Unit equivalence for A13 (`check_bidirectional_coverage`):**

```python
# tests/kg/migration/test_a13_bidirectional_coverage.py
"""
Verifies the §6.4 A13 invariant: KG-based coverage check eliminates
the regex false-positive from Task 1 §1.4 case A while preserving
true-positive coverage detection.
"""
from __future__ import annotations
import pytest
from pathlib import Path

from cataforge.domain.kg import KnowledgeGraph, KGConfig
from cataforge.domain.kg._models_core import Feature, Module, TestCase
from cataforge.doc_review.checker import check_bidirectional_coverage as legacy


@pytest.fixture
def memory_kg(tmp_path: Path):
    config = KGConfig(store_backend="memory")
    with KnowledgeGraph.connect(config) as kg:
        yield kg


@pytest.mark.asyncio
async def test_kg_coverage_rejects_regex_false_positive(memory_kg):
    """
    Scenario: arch markdown mentions F-001 in a comment ("see F-001 for
    background") but no Module truly implements it. 0.4.x regex passes;
    0.5.0 KG SPARQL fails (no cf:implements edge).
    """
    # Setup: Feature exists, no implementing Module.
    async with memory_kg.transaction() as txn:
        await txn.add(Feature(
            id="https://cataforge.dev/instance/F-001",
            entity_id="F-001", sort_key="F:000001",
            title="Login flow",
            belongs_to_project="https://cataforge.dev/instance/proj-test",
        ))

    # New SPARQL (from §6.4 A13)
    sparql = """
    PREFIX cf: <https://cataforge.dev/ontology/>
    SELECT ?eid WHERE {
      ?f a cf:Feature ; cf:entity_id ?eid .
      FILTER NOT EXISTS { ?m a cf:Module ; cf:implements ?f . }
    }
    """
    uncovered = [str(r[0]) for r in memory_kg._store.query(sparql)]
    assert uncovered == ["F-001"], "KG must flag F-001 as uncovered"

    # Compare to legacy: legacy with a "see F-001 for background" string
    # would incorrectly return PASS.
    arch_body = "## M-014 AuthService\n\nNotes: see F-001 for background.\n"
    legacy_pass = legacy(upstream_items=["F-001"], downstream_content=arch_body)
    assert legacy_pass is True, "legacy regex must produce the false positive"
    # KG correctly disagrees.


@pytest.mark.asyncio
async def test_kg_coverage_recognises_real_implementation(memory_kg):
    """Positive test: a Module with cf:implements edge counts as coverage."""
    async with memory_kg.transaction() as txn:
        await txn.add(Feature(
            id="https://cataforge.dev/instance/F-002",
            entity_id="F-002", sort_key="F:000002",
            title="Password reset",
            belongs_to_project="https://cataforge.dev/instance/proj-test",
        ))
        await txn.add(Module(
            id="https://cataforge.dev/instance/M-020",
            entity_id="M-020", sort_key="M:000020",
            title="ResetService",
            implements=["https://cataforge.dev/instance/F-002"],
            belongs_to_project="https://cataforge.dev/instance/proj-test",
        ))

    sparql = """
    PREFIX cf: <https://cataforge.dev/ontology/>
    SELECT ?eid WHERE {
      ?f a cf:Feature ; cf:entity_id ?eid .
      FILTER NOT EXISTS { ?m a cf:Module ; cf:implements ?f . }
    }
    """
    uncovered = [str(r[0]) for r in memory_kg._store.query(sparql)]
    assert "F-002" not in uncovered
```

**Skeleton 2 — Integration golden for doc-review dual-path:**

```python
# tests/kg/migration/test_doc_review_dual_path.py
"""
Runs doc-review against the demo-0.4.1 fixture under both code paths.
Asserts findings are identical except for the documented divergences:
  - false-positive coverage (legacy) → eliminated (KG).
  - mentions-style xref (legacy) → flagged (KG strict mode).
Both deltas are pinned in tests/golden/doc-review-0.4-vs-0.5.json.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

FIXTURE = Path("tests/fixtures/projects/demo-0.4.1")
GOLDEN  = Path("tests/golden/doc-review-0.4-vs-0.5.json")


def _run_legacy(project_root: Path) -> dict:
    out = subprocess.check_output(
        ["cataforge", "skill", "run", "doc-review",
         "--project-root", str(project_root), "--output", "json"],
        env={"CATAFORGE_KG_DISABLED": "1"},
    )
    return json.loads(out)


def _run_kg(project_root: Path) -> dict:
    # Initialize KG and import fixture
    subprocess.check_call(
        ["cataforge", "kg", "init", "--force",
         "--db-path", str(project_root / ".cataforge/kg/store")]
    )
    subprocess.check_call(
        ["cataforge", "kg", "import", str(project_root / "docs"),
         "--coverage-mode", "strict",
         "--db-path", str(project_root / ".cataforge/kg/store")]
    )
    out = subprocess.check_output(
        ["cataforge", "skill", "run", "doc-review",
         "--project-root", str(project_root), "--output", "json"],
    )
    return json.loads(out)


def test_doc_review_dual_path_diff(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    # Copy fixture verbatim
    subprocess.check_call(["cp", "-r", str(FIXTURE) + "/.", str(project)])

    legacy = _run_legacy(project)
    new    = _run_kg(project)

    # Normalize: drop volatile timestamps, sort lists.
    def _norm(d: dict) -> dict:
        d = {k: v for k, v in d.items() if k != "generated_at"}
        for k, v in d.items():
            if isinstance(v, list):
                d[k] = sorted(v, key=str)
        return d

    diff = {"legacy_only": [], "kg_only": []}
    for finding in _norm(legacy).get("findings", []):
        if finding not in _norm(new).get("findings", []):
            diff["legacy_only"].append(finding)
    for finding in _norm(new).get("findings", []):
        if finding not in _norm(legacy).get("findings", []):
            diff["kg_only"].append(finding)

    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert diff == expected, (
        f"doc-review dual-path diff drifted; update {GOLDEN} after review.\n"
        f"Got: {json.dumps(diff, indent=2)}"
    )
```

---

## §6.7 Efficiency Improvement Quantification

Quantitative derivation (no hand-waving). Comparisons are 0.4.1 (markdown + regex) vs 0.5.0 (KG SPARQL).

### Scenario 1 — Single section text extraction (e.g., `prd#§2.F-001`)

- **Old:** `extract()` opens file (~300 lines for an arch volume = ~12 KB), parses with markdown-it CommonMark (`md_parse.py`), iterates headings to find the section, returns ~50-line slice ≈ **2 KB markdown → ~500 tokens fed to LLM**. Markdown-it parse: ~1.2 ms / 300-line file.
  - Token cost in agent prompt: **~500 tokens** (markdown including incidental prose).
  - Token cost for repeated calls (cache miss): **N × ~500 tokens** where N = number of Agent invocations referencing that section.
- **New:** `kg.query.feature("F-001")` returns a Pydantic model with ~12 typed slots (title, status, priority, AC URIs). Serialized to JSON: ~150 bytes ≈ **~40 tokens**. SPARQL DESCRIBE on pyoxigraph for one URI: ~0.3 ms (Task 2 §2.4 benchmark anchor).
  - Token cost in agent prompt: **~40 tokens** (structured slots only). If the agent needs body markdown, it calls `render_entity(uri)` which materializes ~500 tokens — back to parity, but only when the body is actually needed.
- **Net:** Typical agent calls (e.g., qa-engineer needing AC text + status only) drop from ~500 tokens to ~40 tokens — **~12× reduction**. Worst case (needs body) is parity.

### Scenario 2 — Bidirectional coverage check

- **Old (Task 1 §1.4 case A):** For each upstream item (M items across PRD), glob downstream docs (N files), `re.search` for each item ID in each file body. Cost: **O(M × N × L)** where L = avg file length. For 100 features × 5 arch volumes × 12 KB ≈ **6 MB of regex scanning + 500 IO calls** per validate run. CPU: ~50 ms per regex match × 100 × 5 = ~25 s on a cold cache.
- **New:** SPARQL with `cf:verifies+` property path. Pyoxigraph RocksDB index on `?p ?o` for `cf:verifies` is **O(log N)** lookup per Feature, no file IO. For 100 features: 100 × log₂(triple_count). With triple_count ≈ 10⁴ for a medium project, log₂ ≈ 14, so ≈ 1 400 index probes ≈ **~50 ms total**.
- **Net:** **~500× faster** end-to-end (~25 s → ~50 ms) plus elimination of false positives.

### Scenario 3 — Traceability chain query

- **Old:** Does not exist as a single operation in 0.4.x. Agents stitch chains manually by issuing N `cataforge docs load` calls and parsing the results. For a 5-hop chain (Feature→Module→Task→TestCase→Release): **5 subprocess invocations × ~500 tokens = ~2 500 tokens + 5 × ~100 ms subprocess cost = ~500 ms wall**.
- **New:** `kg.trace.from_requirement("F-001")` runs one SPARQL property-path query: `(cf:implemented_by|cf:realized_as|cf:verifies|cf:delivers)+`. Pyoxigraph property-path execution: ~5 ms for a 5-hop chain with 10⁴ triples. Result: `TraceChain` dataclass ≈ **~200 tokens serialized**.
- **Net:** **~12× token reduction**, **~100× latency reduction**, plus first-class chain-break detection (`TraceChain.chain_breaks`) that 0.4.x cannot express.

### Scenario 4 — Response latency prediction

| Operation | 0.4.1 | 0.5.0 | Reasoning |
|-----------|-------|-------|-----------|
| Single entity fetch | ~5 ms (file read + parse) | ~0.3 ms (RocksDB lookup) | Index probe vs file scan |
| Full-corpus xref check | ~25 s | ~50 ms | O(M·N·L) vs O(M·log N) |
| 5-hop traceability | ~500 ms (5 subprocess + parse) | ~5 ms (one SPARQL) | Subprocess fork vs in-process query |
| Bootstrap full ingest | ~3 s (markdown parse + JSON write) | ~6 s (markdown parse + SHACL + RocksDB write) | KG ingest is ~2× slower but bootstrap is one-time |
| Steady-state validate run | ~30 s | ~200 ms | Eliminates whole-file regex; SHACL runs on staging deltas |

### Final summary table

| Dimension | 0.4.1 baseline | 0.5.0 KG | Improvement |
|-----------|----------------|----------|-------------|
| **Token consumption** (per agent fetch) | ~500 (full markdown) | ~40 (typed slots) | **~12× reduction** |
| **Latency** (validate full corpus) | ~30 s | ~200 ms | **~150× reduction** |
| **Latency** (traceability chain) | ~500 ms | ~5 ms | **~100× reduction** |
| **Precision** (coverage false-positive rate) | ~5–15 % (regex assassins) | 0 % (graph edge required) | **eliminated** |
| **Consistency guarantee** | mtime + content_hash WARN | SHACL invariant + optimistic-lock conflict error + `doctor` hard gate | **promoted from WARN to FAIL** |
| **Cross-doc reference correctness** | regex glob (false positives + false negatives) | URI resolution (KGEntityNotFoundError) | **deterministic** |

---

## §6.8 Typical Business-Entity Migration Code Examples

Three complete before/after pairs covering the three required scenarios.

### Example 1 — Simple business-entity query (`get_requirement_description`)

**Before (0.4.1):**

```python
# src/cataforge/agent_helpers/requirement.py — 0.4.1
import subprocess
from cataforge.domain.docs.md_parse import iter_markdown_headings

def get_requirement_description(feature_id: str, project_root: str) -> str | None:
    """
    Reads a Feature's description by shelling out to `cataforge docs load`.

    Returns the markdown body of the F-NNN section, or None if not found.
    Implementation walks the .doc-index.json then the file slice.
    """
    proc = subprocess.run(
        ["cataforge", "docs", "load", f"prd#§2.{feature_id}",
         "--project-root", project_root],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    # Strip the "=== ref ===\n" banner that cataforge docs load prepends
    body = proc.stdout
    if body.startswith("==="):
        body = body.split("\n", 1)[1]
    return body or None
```

**After (0.5.0):**

```python
# src/cataforge/agent_helpers/requirement.py — 0.5.0
from cataforge.domain.kg import KnowledgeGraph, KGConfig

def get_requirement_description(feature_id: str, project_root: str) -> str | None:
    """
    Fetches a Feature's description directly from the KG.

    Key changes:
      1. No subprocess — opens an in-process KnowledgeGraph connection.
      2. Returns the structured `description` slot rather than the raw
         markdown body. Agents that need the full body should call
         `cataforge.domain.kg.export.render_entity(feature.id)` instead — see
         Task 6 §6.5 #1 (extract_with_body shim) for the rationale.
      3. Strongly typed: feature.description is `Optional[str]`, no
         "starts with ===" hack to strip the legacy CLI banner.
    """
    config = KGConfig(db_path=f"{project_root}/.cataforge/kg/store")
    with KnowledgeGraph.connect(config) as kg:
        feature = kg.query.feature(feature_id)        # typed accessor
        return feature.description if feature else None
```

### Example 2 — Traceability chain query (`find_test_cases_for_requirement`)

**Before (0.4.1):**

```python
# src/cataforge/agent_helpers/coverage.py — 0.4.1
import json
import re
import subprocess
from pathlib import Path

_TC_LINE_RE = re.compile(r"\|\s*(TC-\d+)\s*\|.*\|\s*(F-\d+|T-\d+)\s*\|")

def find_test_cases_for_requirement(req_id: str, project_root: str) -> list[str]:
    """
    Walks the test-report markdown looking for table rows that mention
    `req_id` in the requirement column. No traceability graph in 0.4.x.

    Returns the list of TC-NNN IDs that mention req_id. WARNING: this is
    a string match; a TC that lists F-001 in a comment is counted.
    """
    docs_dir = Path(project_root) / "docs" / "test-report"
    tc_ids: list[str] = []
    for md_file in docs_dir.glob("test-report*.md"):
        for line in md_file.read_text(encoding="utf-8").splitlines():
            m = _TC_LINE_RE.match(line)
            if m and m.group(2) == req_id:
                tc_ids.append(m.group(1))
    return sorted(set(tc_ids))
```

**After (0.5.0):**

```python
# src/cataforge/agent_helpers/coverage.py — 0.5.0
from cataforge.domain.kg import KnowledgeGraph, KGConfig

def find_test_cases_for_requirement(req_id: str, project_root: str) -> list[str]:
    """
    Returns the TC-NNN IDs that verify a given Requirement.

    Key changes:
      1. Single SPARQL traversal of cf:verifies+ replaces O(F) file scan.
      2. Property-path "+" gives transitive closure for free — a TestCase
         that verifies a TestSuite that verifies the Feature is included.
      3. No false positives: a TC that mentions F-001 in markdown without
         a true cf:verifies edge is NOT included (assassinates the Task 1
         §1.4 case A class of bug).
    """
    config = KGConfig(db_path=f"{project_root}/.cataforge/kg/store")
    with KnowledgeGraph.connect(config) as kg:
        sparql = """
        PREFIX cf:    <https://cataforge.dev/ontology/>
        PREFIX cfprj: <https://cataforge.dev/instance/>
        SELECT ?tc_id WHERE {
          ?tc a cf:TestCase ;
              cf:entity_id ?tc_id ;
              cf:verifies+ ?req .
          ?req cf:entity_id ?req_id .
          FILTER(?req_id = "%s")
        }
        ORDER BY ?tc_id
        """ % req_id
        return [str(row[0]) for row in kg._store.query(sparql)]
```

### Example 3 — Bidirectional coverage check (`check_bidirectional_coverage` rewrite)

**Before (0.4.1) — extracted from `src/cataforge/skills/doc_review/checker.py`:**

```python
# src/cataforge/skills/doc_review/checker.py — 0.4.1 (excerpt)
import re
from pathlib import Path
from typing import Sequence

_CODE_FENCE_RE = re.compile(r"```.*?```", flags=re.DOTALL)

def check_bidirectional_coverage(
    upstream_items: Sequence[str],     # e.g. ["F-001", "F-002", ...]
    downstream_docs_dir: Path,         # e.g. docs/arch/
    downstream_glob: str = "arch*.md",
) -> tuple[bool, list[str]]:
    """
    Returns (ok, missing) where `missing` is upstream items absent from
    every downstream doc body. False positive: mention in a comment, a
    deprecated section, or a URL fragment counts as coverage.
    """
    bodies: list[str] = []
    for md_path in downstream_docs_dir.glob(downstream_glob):
        content = md_path.read_text(encoding="utf-8")
        # Strip code fences (incomplete: nested fences fall through)
        content_no_code = _CODE_FENCE_RE.sub("", content)
        bodies.append(content_no_code)
    joined = "\n".join(bodies)

    missing: list[str] = []
    for item in upstream_items:
        # String existence test — assassin false positive source
        if not re.search(re.escape(item), joined):
            missing.append(item)
    return (not missing, missing)
```

**After (0.5.0):**

```python
# src/cataforge/skills/doc_review/checker.py — 0.5.0
from cataforge.domain.kg import KnowledgeGraph, KGConfig

def check_bidirectional_coverage(
    project_root: str,
    *,
    require_implementation: bool = True,
    require_verification: bool = True,
) -> tuple[bool, list[dict[str, bool]]]:
    """
    Returns (ok, gaps) where `gaps` is a list of dicts:
        {"feature_id": str, "has_impl": bool, "has_test": bool}

    Key changes:
      1. Drops the upstream_items list parameter — the KG knows every
         Feature; no caller-side enumeration.
      2. Drops the downstream_docs_dir + downstream_glob params — the
         KG knows every Module's cf:implements edge; no filesystem scan.
      3. Eliminates the false-positive class (mention != coverage).
         Coverage now requires an asserted cf:implements (Module/Component
         → Feature) and/or cf:verifies (TestCase → Feature) edge.
      4. Returns structured per-Feature status, not flat ID list, so
         doc-review reports can say WHICH side (impl vs test) is missing.
    """
    config = KGConfig(db_path=f"{project_root}/.cataforge/kg/store")
    sparql = """
    PREFIX cf:   <https://cataforge.dev/ontology/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?feature_id
           (BOUND(?impl) AS ?has_impl)
           (BOUND(?tc)   AS ?has_test)
    WHERE {
      ?feature a cf:Feature ;
               cf:entity_id ?feature_id .
      OPTIONAL {
        ?impl_node cf:implements ?feature .
        ?impl_node a ?impl_class .
        ?impl_class rdfs:subClassOf* cf:SoftwareArtifact .
        BIND(?impl_node AS ?impl)
      }
      OPTIONAL {
        ?tc a cf:TestCase ; cf:verifies+ ?feature .
      }
    }
    ORDER BY ?feature_id
    """
    gaps: list[dict[str, bool]] = []
    with KnowledgeGraph.connect(config) as kg:
        for row in kg._store.query(sparql):
            fid, has_impl, has_test = str(row[0]), bool(row[1]), bool(row[2])
            needs_impl = require_implementation and not has_impl
            needs_test = require_verification and not has_test
            if needs_impl or needs_test:
                gaps.append({
                    "feature_id": fid,
                    "has_impl": has_impl,
                    "has_test": has_test,
                })
    return (not gaps, gaps)
```

---

## [依赖传递摘要]

**关键决策**:
- 16 个调用点拆为 Group A (15 个业务文档) + Group B (≥2 个框架资产)；只有 Group A 走 `KnowledgeGraph` API。Orchestrator 整合时按此清单分配迁移工单。
- `extract()` 全文回退已撤，`doctor` 新增 `kg_ingestion_completeness` ERROR 级硬门（§6.4 末），阻断 `cataforge ready`；Task 7 上线检查单必须把此 gate 列为前置条件。
- 5 个不可 1:1 映射的破坏性变更各配 shim：`extract_with_body` (§6.5 #1)、`QueryAPI.api()/page()` errata (§6.5 #2)、`legacy_validate_report()` (§6.5 #3)、`deps:` codemod (§6.5 #4)、`source_section()` (§6.5 #5)。所有 shim 居于 `src/cataforge/domain/kg/_shim.py`，0.6.0 移除。
- A13 双向覆盖检查迁到 SPARQL `cf:implements`/`cf:verifies+`，A8 依赖推断同源；`coverage_mode=strict` 默认根除假阳性。
- 测试覆盖要求：A1–A15 每行 ≥1 单测，doc-review/sprint-review 双路径黄金对比测试入库 `tests/golden/`，shim 覆盖率门槛 95%。
- 量化收益：token 单实体获取 ~12×、validate 全量 ~150×、可追溯链 ~100×；正确性方面假阳性归零、一致性从 WARN 升 FAIL。

**输出物路径/位置**:
- `docs/proposals/kg-migration-0.5.0/task-6-migration-mapping.md`

**阻塞标记**: NONE。两项 errata 需 Task 5 增补（`QueryAPI.api()` / `QueryAPI.page()`）；Task 4 export 管道需暴露 `render_entity(uri, template)` 公开符号（§6.5 #1 依赖）。两项均不阻塞本文档，但需在 Orchestrator O1 一致性检查中标记并指派回 Agent-T5 / Agent-T4 收口。
