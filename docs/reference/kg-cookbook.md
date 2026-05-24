---
id: ref-kg-cookbook
doc_type: reference
status: stable
---

# KG Cookbook

Task-oriented recipes for the `cataforge kg *` surface.
Companion: [kg-sparql-recipes.md](kg-sparql-recipes.md) (query syntax).
Design reference: [`docs/research/kg-feature-upgrade-design.md`](../research/kg-feature-upgrade-design.md).

## 1 · Day-zero setup

```bash
# Initialise an empty graph store in the project
cataforge kg init

# Run the one-shot migration (legacy `.doc-index.json` → `docs/.doc-graph/`)
cataforge kg migrate

# Verify SHACL conformance (warn-only on first run)
cataforge kg validate
```

Rollback if anything looks wrong:

```bash
cataforge kg migrate --rollback
```

## 2 · Querying the graph

```bash
# Plain SPARQL (always ORDER BY for reproducible output)
cataforge kg query --sparql "SELECT ?id WHERE { ?x cfk:hasId ?id } ORDER BY ?id"

# JSON DSL — short form for relation walks
cataforge kg query --dsl '{"rel": "cfa:validates"}'

# Cypher-lite — single-pattern MATCH ... RETURN
cataforge kg query --cypher "MATCH (t:TestCase)-[:validates]->(f:Feature) RETURN t, f"
```

Hand-written SPARQL files are loaded from disk via `--sparql-file`.

## 3 · Coverage matrices (V-model traceability)

```bash
# Requirements Traceability Matrix (rtm preset)
cataforge kg coverage --preset rtm

# Risk → CodeUnit (mitigates) preset
cataforge kg coverage --preset risk

# Custom: any (rows × cols, via predicate) combination
cataforge kg coverage \
    --rows cfa:Feature --cols cfa:TestCase \
    --via cfa:validates --format markdown
```

Output formats: `table` (default), `json`, `markdown`, `mermaid`.

## 4 · Entity / relation CRUD

```bash
# Add typed entity with display ID
cataforge kg add-entity --type cfa:Feature --id F-001 \
    --iri cfa:prd-acme/F-001 \
    --props '{"rdfs:label": "login", "cfk:definedIn": "cfk:doc/prd-acme"}'

# Inspect every triple where SUBJECT appears in subject position
cataforge kg get-entity cfa:prd-acme/F-001

# Field overwrite via SPARQL UPDATE
cataforge kg update-entity cfa:prd-acme/F-001 --set "cfa:status=active"

# Add / remove a relation
cataforge kg add-relation cfa:arch-acme/M-001 cfa:implements cfa:prd-acme/F-001
cataforge kg remove-relation cfa:arch-acme/M-001 cfa:implements cfa:prd-acme/F-001
```

`update-entity --set 'rdfs:label="new value"'` works the same as `add-relation` for literal predicates — the existing value is replaced atomically.

## 5 · Render markdown from the KG

```bash
# Render every doc-type into docs/<type>/<doc-id>.md
cataforge kg render --all

# Render one doc to stdout
cataforge kg render --doc cfk:doc/prd-acme --template prd.md.j2 --project acme

# Idempotency check — exits 1 if any template's render differs from disk
cataforge kg render --check
```

Pre-commit + PR CI should both run `--check` (design §4.3).

## 6 · Ingest markdown back into the KG

```bash
# Single file — applies 3-way merge with the kg-wins strategy
cataforge kg ingest --file docs/prd/prd-acme.md

# Full sweep — equivalent to the legacy `cataforge docs index`
cataforge kg ingest --all

# Conflict triage
cataforge kg conflicts
cataforge kg resolve <conflict-id> --pick file   # or --pick kg / --pick merge
```

PostToolUse runs `--auto --file <path>` in quiet-fail mode so a user
Edit never blocks; conflicts surface later via `cataforge doctor`.

## 7 · Reasoning and explain

```bash
# Materialise the limited-profile OWL-RL closure
cataforge kg infer            # writes docs/.doc-graph/inferred.nq

# Who transitively depends on this node?
cataforge kg impact cfa:prd-acme/F-001

# Why does (s, p, o) hold? base / inverse / transitive / absent
cataforge kg explain cfa:arch-acme/M-001 cfa:implements cfa:prd-acme/F-001
```

## 8 · Visualisation

```bash
# Mermaid (paste into a markdown viewer)
cataforge kg viz --format mermaid

# DOT (Graphviz)
cataforge kg viz --format dot

# SVG (requires `dot` on PATH; falls back to DOT text if missing)
cataforge kg viz --format svg --out kg.svg

# Anchored / scoped views
cataforge kg viz --node cfa:prd-acme/F-001 --depth 3 --format mermaid
cataforge kg viz --scope cfa:Feature --format mermaid
```

## 9 · Working with adapters

```bash
# List every registered adapter (built-ins + plugins)
cataforge kg adapter list

# Show one adapter's JSON Schema for its config block
cataforge kg adapter show feature_authoring

# Run pre_dispatch_context against the live KG with a config + params
cataforge kg adapter context feature_authoring \
    --config config.json \
    --params '{"doc_id": "prd-acme", "doc_iri": "cfk:doc/prd-acme"}'

# Apply an agent's output JSON via the adapter's write-back schema
cataforge kg adapter write-back feature_authoring \
    --config config.json \
    --output output.json \
    --invocation-id manual-2026-05-24
```

`cataforge kg adapter-migrate` injects the canonical `kg_adapter:`
block into every agent / skill (and writes default JSON Schemas under
`.cataforge/skills/doc-gen/schemas/`). Idempotent — re-running is a
no-op once the canonical block is in place.

## 10 · Template lint + performance budget

```bash
# Static checks: Jinja2 syntax + SPARQL ORDER BY + deprecated placeholders
cataforge kg template-lint

# Perf budget gate (cross-machine variance → warn-only by default)
cataforge kg benchmark
```

The budget file lives at `.cataforge/kg/perf-budget.json`; tighten it
project-by-project as your fixture grows.

## 11 · Export

```bash
cataforge kg export --format turtle  --out kg.ttl
cataforge kg export --format jsonld  --out kg.jsonld
cataforge kg export --format nquads  --out kg.nq
cataforge kg export --format graphml --out kg.graphml
```

GraphML is the lossy "nodes + edges only" form — pick `turtle` or
`jsonld` when you need round-trip fidelity.

## 12 · Plugin integration

Drop a `kg.plugins` block into `.cataforge/framework.json`:

```json
{
  "kg": {
    "plugins": [
      {"module": "cataforge_kg_oxigraph", "hook": "StoreBackendPlugin"},
      {"module": "myproj_kg_extras",      "hook": "KGAdapterPlugin"}
    ]
  }
}
```

Plugin modules need a top-level `register(registry)` function. The six
hook names are listed in [`src/cataforge/kg/plugin_hooks.py`](../../src/cataforge/kg/plugin_hooks.py).
