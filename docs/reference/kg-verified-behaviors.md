# KG · Verified behaviors and remaining follow-ups

For each `[待验证]` marker raised in the 0.5.0 KG design (task-3 / task-4 / task-5), this
file records the disposition: verified during implementation, deferred with a
documented escape hatch, or rolled into a downstream sub-PR.

## Verified during Alpha

### pyoxigraph SPARQL property-path `a/rdfs:subClassOf*` on 0.5.x
*Origin*: task-4 / README open follow-ups · spike-2 §2.1 (issue
[CataForge#142](https://github.com/lync-cyber/CataForge/issues/142)).

pyoxigraph 0.5.x performs no OWL/RDFS entailment. `cataforge kg init`
materializes `rdfs:subClassOf` triples from `core.yaml` `is_a` chains via
[`bootstrap_subclass_axioms`](../../src/cataforge/domain/kg/_store.py) so property-path
queries traverse the closure directly.

Evidence: [tests/kg/test_store.py::test_subclass_closure_query_returns_page_for_screen](../../tests/kg/test_store.py)
inserts a `cf:Page` instance and asserts `SELECT ?s WHERE { ?s a/rdfs:subClassOf* cf:Screen }`
returns that instance. The same mechanic is the basis for `QueryAPI.requirement()`,
`QueryAPI.all_entities(types=…)`, and the doctor `kg_ingestion_completeness`
SPARQL enumeration.

### `belongs_to_work_unit` polymorphic accessor
*Origin*: task-3 §3 / task-5 `[待验证]`.

The design proposal flagged "is LinkML `union_of` syntax sufficient, or does this
need a SPARQL CONSTRUCT inference rule?" The schema resolves it without either:
`belongs_to_work_unit` has `range: WorkUnit`, and `Phase` / `Sprint` / `Iteration`
each `is_a: WorkUnit` ([core.yaml lines 410–438](../../src/cataforge/domain/kg/schemas/core.yaml)).
Polymorphic queries fall back on the verified `a/rdfs:subClassOf*` mechanic above —
no CONSTRUCT rule, no `union_of` workaround.

### TestCase ID prefix strictness (`TC-NNN`)
*Origin*: task-3 §3.9 decision 1.

`core.yaml` declares `Pattern: ^TC-[0-9]{3,}$` for the `TestCase.entity_id` slot, and
`scripts/codegen_kg_schema.py` produces `_generated/core_shapes.ttl` containing the
matching SHACL `sh:pattern` constraint. Codegen smoke-test
[`tests/kg/test_codegen.py`](../../tests/kg/test_codegen.py) asserts the regeneration
is byte-stable. Historical TC- prefix variance (the proposal's open question) is
treated as a migration concern: the ingest codemod skips non-conforming matches
and the doctor gate surfaces them as missing.

### Schema codegen produces well-formed Pydantic + SHACL
*Origin*: task-3 `[待验证]` (LinkML codegen behavior with non-trivial slots).

`scripts/codegen_kg_schema.py` runs `gen-pydantic` and `gen-shacl` over `core.yaml`
and `governance.yaml`; the generated artefacts in `src/cataforge/domain/kg/_generated/` are
imported at runtime by the ingest pipeline and the export pipeline. Failure modes
are caught by `tests/kg/test_codegen.py` (byte-stable regeneration) and
`tests/kg/test_ingest.py` (live ingest exercises the generated types).

### SHACL `sh:closed true` enforcement at runtime
*Origin*: task-3 §6 / task-5 `[待验证]`.

`core.yaml` declares closed shapes per class, and `gen-shacl` materializes them
into `_generated/core_shapes.ttl`. `--shacl` runs them at runtime:
[`validate.py::_run_shacl`](../../src/cataforge/domain/kg/validate.py) bridges the
pyoxigraph store into an rdflib `Graph` (`_pyoxigraph_to_rdflib`) and validates it
with `pyshacl`. `shacl_skipped = True` is reported only when the optional
`[shacl]` extra (`pyshacl` + `rdflib`) is absent or the shapes file is missing;
when present, conformance and per-shape violations are returned.

Evidence: [`tests/kg/test_shacl_bridge.py`](../../tests/kg/test_shacl_bridge.py)
covers the term-level round-trip, datatype handling, the skip paths when deps or
shapes are missing, and both the violation-detected and conforming-data cases.
Write-time schema constraints inside the ingest codemod (`verify_after_write`)
back-stop this for environments without the extra installed.

## Deferred — known escape hatch, no Alpha blocker

### Embedded LLM client for natural-language query
*Origin*: task-5 §5.7 `[待验证]`.

The natural-language query surface ships as the `context` skill's query branch (B1): a host
agent translates a question into read-only SPARQL grounded on the schema card
from `cataforge kg schema-context`, then runs it through the write-guarded
`kg query`. A baked-in embedded LLM client (B2 — e.g. an `anthropic` client
behind its own optional extra, for headless/CI translation) is deferred to
0.6.0+; it reuses the same schema card as its system prompt. The
`cataforge.domain.kg.nl_query` surface in the meantime stays framework-free:
the caller injects any `.invoke(prompt)`-compatible client.

## Sub-PR 6 verification additions

The following live in this branch and back the dispositions above:

* `tests/kg/test_reconcile.py` — confirms the per-doc_type drift detector closes
  Alpha exit condition 2 (doctor gate ERROR-enforced for one full reconcile
  cycle is now meaningful).
* `tests/kg/test_compare_read.py` — confirms the content-hash sampler raises
  alarms on mutated source body and on FS-only entities, and stays silent on a
  freshly-ingested fixture.
* `_DEFAULT_DOC_TYPE_MAP` in [`docs/loader.py`](../../src/cataforge/domain/docs/loader.py)
  now carries the canonical `test → test-report` alias, matching the
  `KGConfig.kg_active_doc_types` default and the doctor module's internal map.
  This removes the per-module fork that previously diverged.
