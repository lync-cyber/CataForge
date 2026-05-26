# Task 2 — Python Knowledge-Graph Tool-Stack Selection

> CataForge 0.5.0 · KG Migration Proposal Series

---

## §2.1 Candidate Survey

### Layer A — Graph Storage / DB

| Candidate | Type | Embedded? | Storage backend |
|-----------|------|-----------|-----------------|
| **RDFLib** (in-memory) | RDF triple store | Yes (in-process) | In-memory only (or SQLite plugin) |
| **pyoxigraph** | RDF triple store + SPARQL engine | Yes (in-process) | RocksDB (disk) or in-memory |
| **Kùzu** | Property graph (Cypher) | Yes (in-process) | Custom columnar on-disk | 
| **Neo4j** (Python driver) | Property graph (Cypher) | No — requires standalone server | Remote bolt |
| **DuckDB + DuckPGQ** | Relational + SQL/PGQ graph queries | Yes (in-process) | Custom columnar on-disk |
| **ArangoDB** | Multi-model (doc + graph) | No — requires standalone server | Remote HTTP |

### Layer B — Ontology / Schema Modeling

| Candidate | Paradigm | Output formats |
|-----------|----------|----------------|
| **LinkML** | YAML-first schema, OOP + OWL alignment | Python dataclasses, Pydantic models, JSON Schema, RDF/OWL, SHACL |
| **Owlready2** | Python-object OWL 2.0 ontology authoring | OWL/XML, RDF/XML; HermiT reasoner integration |
| **RDFLib-OWL / OWL-RL** | Pure-Python OWL RL rule-based reasoning | RDF graphs (no code-gen) |
| **pylode** | OWL documentation generator | HTML, Markdown (read-only; not a modeling tool) |
| **Pydantic + JSON Schema** | Type-annotated Python models | JSON Schema; no native RDF export |

### Layer C — Graph Query

| Candidate | Query language | Engine |
|-----------|----------------|--------|
| **pyoxigraph SPARQL** | SPARQL 1.1 (query + update + federation) | Rust (via pyoxigraph); zero external deps |
| **RDFLib SPARQL** | SPARQL 1.1 | Pure Python; slower on large graphs |
| **SPARQLWrapper** | SPARQL 1.1 | HTTP wrapper for remote SPARQL endpoints |
| **Kùzu / neo4j-python-driver** | Cypher (openCypher) | Kùzu embedded; Neo4j requires server |
| **DuckPGQ** | SQL/PGQ (ISO SQL:2023 graph extension) | DuckDB community extension |

### Layer D — Python Integration

| Candidate | Role | Highlights |
|-----------|------|------------|
| **oxrdflib** | rdflib store backed by pyoxigraph | Drop-in; bridges both APIs |
| **LinkML gen-pydantic / gen-python** | Code generation from schema | Emits typed Pydantic v2 models from YAML schema; RDF round-trip via linkml-runtime |
| **pyshacl** | RDF graph validation | SHACL Core + SHACL-SPARQL; reports violations as RDF or text |
| **langchain-community RdfGraph** | LLM integration | Wraps rdflib for chain-of-thought SPARQL generation |
| **sparql-llm** | Text-to-SPARQL with schema context | RAG-based; schema injection for hallucination reduction |

---

## §2.2 Per-Candidate Evaluation

All version dates verified against PyPI release history and GitHub commits pages (fetched May 2026).

### A1 · RDFLib

| Attribute | Value |
|-----------|-------|
| Latest version | 7.6.0 |
| Release date | February 13, 2026 |
| Last commit (GitHub) | May 5, 2026 |
| 12-month commit frequency | Active; ~50 merged PRs in rolling year |
| Maintainer risk | Low — volunteer org with multiple active contributors |
| Python 3.10+ | Yes (≥3.8.1; fully tested on 3.10–3.13) |
| LLM integration cases | LangChain `RdfGraph`; LlamaIndex KG store; sparql-llm |
| License | BSD-3-Clause |
| Embedded | Yes (in-memory); disk storage requires SQLAlchemy plugin or oxrdflib |

### A2 · pyoxigraph

| Attribute | Value |
|-----------|-------|
| Latest version | 0.5.8 |
| Release date | April 28, 2026 |
| Last commit (GitHub, oxigraph/oxigraph) | May 24, 2026 |
| 12-month commit frequency | Very high; multiple commits per week |
| Maintainer risk | Low-medium — primary author @Tpt; growing contributor base |
| Python 3.10+ | Yes (≥3.8; tested 3.10–3.13; ships pre-built wheels) |
| LLM integration cases | via oxrdflib→rdflib→LangChain; flexible-graphrag (March 2026 demo) |
| License | MIT OR Apache-2.0 (dual) |
| Embedded | Yes — RocksDB bundled in wheel; no external process |

### A3 · Kùzu

| Attribute | Value |
|-----------|-------|
| Latest version | 0.11.3 |
| Release date | ~May 2026 (PyPI metadata; repo archived Oct 10, 2025) |
| Last commit (GitHub) | October 10, 2025 — **repository archived read-only** |
| 12-month commit frequency | Zero since archival |
| Maintainer risk | **Critical** — project archived; future is unclear |
| Python 3.10+ | Not declared in wheel metadata |
| LLM integration cases | langchain-kuzu; graphiti-core (active bugs on Windows 2026) |
| License | MIT |
| Embedded | Yes |

> **Verdict:** Kùzu is **eliminated** — archived repository is a hard stop per project constraint (no library deprecated/abandoned).

### A4 · Neo4j (Python driver)

| Attribute | Value |
|-----------|-------|
| Latest version | 6.2.0 |
| Release date | May 4, 2026 |
| Last commit (GitHub) | Active |
| Maintainer risk | Low — Neo4j Inc. backed |
| Python 3.10+ | Yes (≥3.10) |
| LLM integration cases | Extensive (LangChain, LlamaIndex, Neo4j GenAI stack) |
| License | Apache-2.0 |
| Embedded | **No** — requires standalone Neo4j server |

> **Verdict:** Eliminated for main backend — violates embedded-operation constraint.

### A5 · DuckDB + DuckPGQ

| Attribute | Value |
|-----------|-------|
| Latest version | DuckDB 1.5.3 (Feb 26, 2025); DuckPGQ community extension |
| Maintainer risk | Low — DuckDB Labs; DuckPGQ is community/research origin |
| Python 3.10+ | Yes (≥3.10) |
| LLM integration cases | Limited; SQL/PGQ not yet supported in major LLM graph frameworks |
| License | MIT |
| Embedded | Yes |

> **Verdict:** Useful for analytical cross-document queries, but SQL/PGQ has no SPARQL 1.1 compatibility, no native RDF support, and no current LLM-framework integration. Not suitable as primary KG store.

### B1 · LinkML

| Attribute | Value |
|-----------|-------|
| Latest version | 1.11.1 |
| Release date | May 20, 2026 |
| Last commit (GitHub, linkml/linkml) | May 21, 2026 |
| 12-month commit frequency | Very high; multiple releases per month |
| Maintainer risk | Low — NCATS/NIH backed; 30+ contributors |
| Python 3.10+ | Yes (≥3.10 required) |
| LLM integration cases | LinkML schema → JSON Schema → LLM structured output; KG extraction pipelines (arxiv 2511.16935, Nov 2025) |
| License | Apache-2.0 |

### B2 · Owlready2

| Attribute | Value |
|-----------|-------|
| Latest version | 0.50 |
| Release date | February 5, 2026 |
| Last commit | BitBucket (primary); inferred active from Feb 2026 release |
| Maintainer risk | **High** — single maintainer (Jean-Baptiste Lamy); BitBucket repo, not GitHub |
| Python 3.10+ | Yes (≥3.6) |
| LLM integration cases | Minimal — no native LangChain/LlamaIndex integration documented |
| License | LGPL-3.0-or-later |

> **Verdict:** Single-maintainer risk + LGPL copyleft concern + no code-generation to Pydantic. Secondary candidate only.

### B3 · RDFLib-OWL / OWL-RL (owl-rl package)

Provides OWL RL reasoning over rdflib graphs. Not a schema-authoring tool — cannot generate typed Python models. Useful as an optional reasoning layer but insufficient as a standalone schema layer.

### C1 · pyoxigraph SPARQL

Rust-native SPARQL 1.1 engine exposed via pyoxigraph. Covers SELECT, CONSTRUCT, ASK, DESCRIBE, UPDATE, and federated SERVICE clauses. No external process. Sub-millisecond queries on graphs up to millions of triples in benchmarks. **This is the selected query engine.**

### C2 · RDFLib SPARQL

Pure-Python SPARQL 1.1 implementation. Correct but orders of magnitude slower than pyoxigraph at scale. Retained as fallback/testing via the `memory` store backend.

### C3 · SPARQLWrapper

Last released March 13, 2022 — **over 36 months ago**. Eliminated per constraint (no library >18 months since last release without active maintenance signal).

### D1 · oxrdflib

Version 0.5.0, released September 13, 2025. Provides a pyoxigraph-backed store that is a drop-in for rdflib's default store. Enables the full rdflib API (including LangChain's `RdfGraph`) while delegating storage and SPARQL to pyoxigraph. **Selected as the bridge layer.**

### D2 · pyshacl

Version 0.31.0, released January 16, 2026. Last commit January 16, 2026. SHACL Core + SHACL-SPARQL + SHACL-JS (optional). Apache-2.0 license. Pure Python (depends on rdflib). **Selected as optional validation layer.**

### D3 · LinkML gen-pydantic

Part of LinkML 1.11.1. Generates Pydantic v2 models from YAML LinkML schema. Supports validators, enumerations, and inheritance. linkml-runtime (1.11.1, May 20, 2026) provides serialization round-trips to YAML, JSON, and RDF. CC0-1.0 license. **Selected as the code-generation layer.**

---

## §2.3 Selection Scoring Matrix

Scoring scale: 0 (fails) / 1 (poor) / 2 (adequate) / 3 (good) / 4 (excellent)

Dimensions:
- **Embedded**: runs in-process, no mandatory server
- **Recency**: last release ≤6 months from May 2026
- **Activity**: commit frequency over last 12 months
- **Maintainer**: multi-contributor or institutional backing
- **Py310+**: explicit Python 3.10+ support
- **RDF/SPARQL**: native SPARQL 1.1 + RDF support
- **Code-gen**: generates typed Python from schema
- **Validation**: schema constraint enforcement
- **LLM-int**: documented LLM framework integration

### Storage / DB Layer

| Candidate | Embedded | Recency | Activity | Maintainer | Py310+ | RDF/SPARQL | **Total** |
|-----------|----------|---------|----------|------------|--------|------------|-----------|
| pyoxigraph | 4 | 4 | 4 | 3 | 4 | 4 | **23** |
| RDFLib | 3 | 4 | 4 | 4 | 4 | 4 | **23** |
| DuckDB+PGQ | 4 | 3 | 4 | 3 | 4 | 0 | **18** |
| Kùzu | 4 | 0 | 0 | 0 | 2 | 0 | **6** |
| Neo4j | 0 | 4 | 4 | 4 | 4 | 1 | **17** |
| ArangoDB | 0 | 4 | 4 | 4 | 4 | 0 | **16** |

### Ontology / Schema Layer

| Candidate | Embedded | Recency | Activity | Maintainer | Py310+ | Code-gen | Validation | LLM-int | **Total** |
|-----------|----------|---------|----------|------------|--------|----------|------------|---------|-----------|
| LinkML | 4 | 4 | 4 | 4 | 4 | 4 | 3 | 3 | **30** |
| Owlready2 | 4 | 3 | 2 | 1 | 4 | 1 | 2 | 1 | **18** |
| RDFLib-OWL | 4 | 4 | 4 | 4 | 4 | 0 | 1 | 2 | **23** |
| pylode | 4 | 2 | 2 | 2 | 4 | 0 | 0 | 0 | **14** |
| Pydantic only | 4 | 4 | 4 | 4 | 4 | 4 | 3 | 4 | **27** |

### Query Layer

| Candidate | Embedded | Recency | Activity | SPARQL 1.1 | Performance | LLM-int | **Total** |
|-----------|----------|---------|----------|------------|-------------|---------|-----------|
| pyoxigraph SPARQL | 4 | 4 | 4 | 4 | 4 | 3 | **23** |
| RDFLib SPARQL | 4 | 4 | 4 | 4 | 2 | 4 | **22** |
| SPARQLWrapper | 0 | 0 | 1 | 4 | 1 | 1 | **7** |
| Kùzu/Cypher | 4 | 0 | 0 | 0 | 3 | 2 | **9** |
| DuckPGQ | 4 | 3 | 3 | 0 | 3 | 0 | **13** |

### Python Integration Layer

| Candidate | Role | Recency | Activity | Embedded | LLM-int | **Total** |
|-----------|------|---------|----------|----------|---------|-----------|
| oxrdflib | Bridge | 3 | 3 | 4 | 3 | **16** |
| LinkML gen-pydantic | Code-gen | 4 | 4 | 4 | 3 | **15** |
| pyshacl | Validation | 3 | 3 | 4 | 2 | **12** |
| langchain RdfGraph | LLM bridge | 4 | 4 | 4 | 4 | **16** |
| SPARQLWrapper | Remote query | 0 | 0 | 0 | 1 | **1** |

---

## §2.4 Recommended Stack

### Recommendation

```
pyoxigraph 0.5.x   — storage + SPARQL engine (RocksDB embedded)
oxrdflib 0.5.x     — rdflib-compatible API bridge
rdflib 7.6.x       — RDF graph API, serialization, ecosystem compatibility
LinkML 1.11.x      — schema authoring (YAML) → Pydantic code generation → RDF/OWL export
pyshacl 0.31.x     — SHACL validation (optional, activated by KGConfig.validation)
```

### Why This Combination vs. Rejected Alternatives

**vs. Owlready2 as ontology layer:**
Owlready2 requires Java (via HermiT reasoner) for OWL reasoning, carries a single-maintainer risk, uses LGPL which complicates downstream relicensing, and cannot generate Pydantic models. LinkML produces typed Pydantic v2 models directly from YAML schemas — those models become the primary Python API surface for agents — and emits SHACL shapes and OWL axioms from the same source file. LinkML also natively supports multi-valued slots, inheritance, and enum constraints in a way that maps cleanly to both RDF and JSON Schema, enabling schema-to-LLM structured output without a separate translation step.

**vs. Kùzu as storage layer:**
Kùzu's GitHub repository was archived read-only on October 10, 2025. No commits, no security patches, and no compatibility updates will occur. Active bugs on Windows were reported in May 2026 (graphiti-core issue #1469). Despite its attractive embedded property-graph model, the lifecycle risk is unacceptable for a framework dependency.

**vs. Neo4j as storage layer:**
Neo4j requires a standalone server process, violating the embedded-operation constraint. It would impose mandatory infrastructure on every end-user install. Additionally, the Cypher query language has no interoperability with SPARQL 1.1 standards, preventing use of the broad W3C RDF/SHACL/OWL ecosystem.

**vs. DuckDB + DuckPGQ as storage layer:**
DuckDB has no native RDF support. SQL/PGQ is SQL:2023 and is not SPARQL 1.1 compatible; no major LLM agent framework (LangChain, LlamaIndex, Haystack) has a DuckPGQ integration as of May 2026. It also lacks schema-level ontology support, making cross-SDLC semantic relationship resolution require hand-written JOIN logic rather than declarative ontological inference.

### How the Stack Addresses the Three Structural Defects

**Defect 1 — LLM query-token inefficiency**

The current system serializes full documents into LLM context windows for every cross-document reference check. With pyoxigraph as the store, agents issue targeted SPARQL SELECT queries over named graphs — retrieving only the triples relevant to a specific entity (e.g., `SELECT ?component ?test WHERE { :Feature-X :implementedBy ?component . ?test :covers ?component }`) rather than loading entire documents. pyoxigraph's Rust-native engine processes these queries in sub-millisecond time, making it practical to issue many small queries rather than one large context dump.

**Defect 2 — Doc rot from manual maintenance**

LinkML schema definitions for each SDLC entity (Requirement, Feature, Component, Task, TestCase, Deployment) are single-source: the YAML schema generates both the Pydantic Python API and the RDF/OWL ontology. When an agent updates a triples graph, the idempotent Markdown export (graph → Markdown) reflects the change automatically. SHACL shapes generated from the same LinkML schema enforce structural integrity on every write, so inconsistencies are caught at ingest rather than discovered during review.

**Defect 3 — Cross-document semantic relationships via regex (false positives / false negatives)**

Regex matching resolves references by text similarity. RDF named graphs with explicit `owl:sameAs`, `rdfs:seeAlso`, and domain-specific object properties (`:traces`, `:implementedBy`, `:verifiedBy`) encode relationships as typed triples. SPARQL CONSTRUCT queries can materialize transitive closure (`:verifiedBy+`) across the full SDLC chain. This eliminates both false positives (no coincidental string matches) and false negatives (no missed references due to synonym variation or abbreviation).

### Known Limitations and Risks

1. **pyoxigraph single-primary-author risk.** The Rust codebase (oxigraph) has a primary author (@Tpt) with growing but not yet large contributor base. A Rust compilation issue on an exotic platform could block a release. Mitigation: pre-built wheels exist for all major platforms (Linux x86_64/aarch64, macOS, Windows); fall back to `memory` store for CI.

2. **LinkML schema migration tooling is immature.** LinkML has no built-in migration runner for evolving schemas in production graphs (e.g., renaming a slot). Schema version changes require manual SPARQL UPDATE migrations. Mitigation: pin the LinkML schema version in pyproject.toml; maintain a `kg/migrations/` directory with numbered SPARQL UPDATE scripts per schema version bump.

3. **SPARQL learning curve for agent authors.** Agents that previously relied on Markdown text search must be rewritten to issue SPARQL queries. This is a capability requirement change, not just a library swap. Mitigation: the LinkML-generated Pydantic models expose a typed Python API; a thin `GraphRepository` abstraction can hide SPARQL from most agents, exposing only `find_by()` / `relate()` / `trace()` methods.

4. **RocksDB disk writes in restricted environments.** Some CI environments (containers with read-only filesystems, certain cloud sandbox runtimes) cannot write to disk. Mitigation: `KGConfig.store_backend = "memory"` covers all test scenarios; RocksDB is only activated in local and production deploys.

5. **pyshacl performance on large validation cycles.** pySHACL is pure Python and can be slow on graphs with hundreds of thousands of triples when validating complex recursive SHACL shapes. Mitigation: validation is opt-in (`KGConfig.validation = false` by default); run only on commit/export, not on every triple update.

---

## §2.5 Minimum-Viable Install Example

### pyproject.toml dependencies

```toml
[project]
name = "cataforge"
requires-python = ">=3.10"

dependencies = [
    # KG storage + SPARQL engine (RocksDB embedded, pre-built wheels)
    "pyoxigraph>=0.5.8",
    # rdflib-compatible API bridge over pyoxigraph
    "oxrdflib>=0.5.0",
    # RDF graph API, serialization (Turtle/JSON-LD/N-Triples), ecosystem glue
    "rdflib>=7.6.0",
    # Schema authoring → Pydantic v2 code-gen → OWL/SHACL export
    "linkml>=1.11.1",
    "linkml-runtime>=1.11.1",
]

[project.optional-dependencies]
# Activate with: pip install cataforge[kg-validation]
kg-validation = [
    "pyshacl>=0.31.0",
]
```

### Hello-Graph snippet (≤30 lines)

```python
"""hello_graph.py — create, populate, query a CataForge KG (embedded RocksDB)."""
import tempfile
from pathlib import Path
from pyoxigraph import Store, NamedNode, Triple, Literal

# --- 1. Open an embedded store (RocksDB on disk, or memory for tests) ----------
store_path = Path(tempfile.mkdtemp()) / "kg"
store = Store(str(store_path))          # omit path for in-memory: Store()

# --- 2. Define namespace shortcuts -----------------------------------------------
CF = "https://cataforge.dev/kg#"
req  = NamedNode(CF + "Req-001")
feat = NamedNode(CF + "Feature-Auth")
p_traces = NamedNode(CF + "traces")
p_label  = NamedNode("http://www.w3.org/2000/01/rdf-schema#label")

# --- 3. Add triples (Feature traces back to Requirement) -------------------------
store.add(Triple(feat, p_traces,  req))
store.add(Triple(feat, p_label,   Literal("User authentication flow")))
store.add(Triple(req,  p_label,   Literal("REQ-001: Users must authenticate")))

# --- 4. SPARQL SELECT query -------------------------------------------------------
results = store.query("""
    PREFIX cf: <https://cataforge.dev/kg#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?feature ?featureLabel ?reqLabel WHERE {
        ?feature cf:traces ?req .
        ?feature rdfs:label ?featureLabel .
        ?req     rdfs:label ?reqLabel .
    }
""")

for row in results:
    print(f"Feature : {row['featureLabel']}")
    print(f"Traces  → {row['reqLabel']}")

store.close()
```

Expected output:

```
Feature : User authentication flow
Traces  → REQ-001: Users must authenticate
```

---

## [依赖传递摘要]

**关键决策:**

- 存储 + SPARQL 引擎：`pyoxigraph>=0.5.8`（RocksDB 嵌入式，无外部进程）；测试后端为 `Store()`（内存）。`KGConfig.store_backend` 仅支持 `"oxigraph"` 和 `"memory"` 两值。
- 本体 / 模式层：`linkml>=1.11.1`（YAML 单源 → Pydantic v2 代码生成 + OWL/SHACL 导出）。每个 SDLC 实体（Requirement、Feature、Component、Task、TestCase、Deployment）均需在 `kg/schema/*.yaml` 中定义 LinkML class。
- Python API 桥接：`oxrdflib>=0.5.0` 使 rdflib 生态（含 LangChain `RdfGraph`）可直接使用 pyoxigraph 后端。
- 可选验证：`pyshacl>=0.31.0`（`kg-validation` extra；默认关闭）。
- **淘汰候选**：Kùzu（仓库已归档）、Neo4j（需独立服务器）、SPARQLWrapper（36 个月未发版）。
- 下游 Task 3（schema 设计）**必须**以 LinkML YAML 格式定义所有实体；Task 4（agent 集成）**必须**通过 SPARQL SELECT/CONSTRUCT 访问图，而非全文扫描。

**输出物路径:** `docs/proposals/kg-migration-0.5.0/task-2-toolstack.md`

**阻塞标记:** NONE
