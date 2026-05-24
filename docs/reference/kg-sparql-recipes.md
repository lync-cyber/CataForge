---
id: ref-kg-sparql-recipes
doc_type: reference
status: stable
---

# KG SPARQL Recipes

Reusable SPARQL fragments for the CataForge ontology. Pair with
[kg-cookbook.md](kg-cookbook.md) (CLI surface).

## 0 · Setup

Every recipe runs against the L0/L1/L2 prefix header that
`cataforge kg query` injects automatically:

```sparql
PREFIX cfk:  <https://cataforge.dev/ontology/kernel#>
PREFIX cfp:  <https://cataforge.dev/ontology/process#>
PREFIX cfa:  <https://cataforge.dev/ontology/artifact#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX sh:   <http://www.w3.org/ns/shacl#>
```

> All queries must end with `ORDER BY` for byte-stable render output
> (design §4.3 / R-03 / R-07). `template-lint` enforces this.

## 1 · Selecting entities by type

```sparql
# Every Feature with its display ID and label
SELECT ?iri ?id ?label
WHERE {
  ?iri a cfa:Feature ;
       cfk:hasId ?id ;
       rdfs:label ?label .
} ORDER BY ?id
```

## 2 · Filtering by parent document

```sparql
# Features defined in one specific PRD
SELECT ?id ?label
WHERE {
  ?f a cfa:Feature ;
     cfk:hasId ?id ;
     rdfs:label ?label ;
     cfk:definedIn <https://cataforge.dev/ontology/kernel#doc/prd-acme> .
} ORDER BY ?id
```

In adapters / templates the doc IRI is parameterised:

```sparql
# Same query, parameterised — used by feature_authoring adapter
SELECT ?id ?label
WHERE {
  ?f a cfa:Feature ; cfk:hasId ?id ; rdfs:label ?label ;
     cfk:definedIn $doc_iri .
} ORDER BY ?id
```

`$doc_iri` is a `string.Template` placeholder (NOT `${doc_iri}` — the
`{}` would collide with SPARQL `WHERE { ... }` blocks). The adapter
runtime substitutes safely-quoted IRIs.

## 3 · Traversing a relation

```sparql
# Modules that implement features in a given PRD
SELECT ?module ?feature
WHERE {
  ?module a cfa:Module ;
          cfa:implements ?feature .
  ?feature a cfa:Feature ;
           cfk:definedIn $prd_doc_iri .
} ORDER BY ?module ?feature
```

## 4 · Transitive dependencies

`cfa:dependsOn` is `owl:TransitiveProperty`, so the `+` operator
walks the closure automatically:

```sparql
# Everything that transitively depends on a given module
SELECT DISTINCT ?dep
WHERE {
  ?dep cfa:dependsOn+ <https://cataforge.dev/ontology/artifact#arch-acme/M-001> .
} ORDER BY ?dep
```

The CLI exposes this as `cataforge kg impact <node>`.

## 5 · Coverage / gap detection

```sparql
# Features with NO validating TestCase (RTM gaps)
SELECT ?feature
WHERE {
  ?feature a cfa:Feature .
  FILTER NOT EXISTS {
    ?tc a cfa:TestCase ;
        cfa:validates ?feature .
  }
} ORDER BY ?feature
```

Preset shortcut: `cataforge kg coverage --preset rtm` returns the
inverse view (full matrix + gap list).

## 6 · Inverse / symmetric materialisation

The reasoning layer materialises `owl:inverseOf` both directions, so
you can query either way after `cataforge kg infer`:

```sparql
# Features implemented by at least one module (forward predicate)
SELECT ?feature
WHERE {
  ?m a cfa:Module ; cfa:implements ?feature .
} ORDER BY ?feature

# Same set via the inverse — equivalent after reasoning
SELECT ?feature
WHERE {
  ?feature cfa:implementedBy ?m .
} ORDER BY ?feature
```

## 7 · Property paths — alternatives + zero-or-one

```sparql
# Any node referenced by a Feature, including via dependsOn chains
SELECT DISTINCT ?target
WHERE {
  ?f a cfa:Feature .
  ?f (cfa:references | cfa:dependsOn+) ?target .
} ORDER BY ?target
```

## 8 · ASK — boolean checks

```sparql
ASK { ?x a cfa:Feature }
```

ASK queries are exempt from the `ORDER BY` lint rule (they return a
single boolean — ordering is meaningless).

## 9 · CONSTRUCT (advanced)

`RDFLibStore.query` deliberately returns only SELECT / ASK rows;
CONSTRUCT-shaped output needs `update(...)` materialised into a
named graph then re-queried. Avoid CONSTRUCT inside render templates
— the round-trip overhead defeats render idempotency.

## 10 · DSL quick-reference

Equivalent to common SPARQL patterns:

| DSL | SPARQL equivalent |
|---|---|
| `{"rel": "cfa:validates"}` | `SELECT ?src ?dst WHERE { ?src cfa:validates ?dst } ORDER BY ?src ?dst` |
| `{"rel": "cfa:implements", "src_type": "cfa:Module"}` | adds `?src a cfa:Module .` |
| `{"rel": "cfa:dependsOn", "src": "cfa:m/M-001"}` | adds `FILTER (?src = <expanded-iri>)` |

The DSL is intentionally narrow — three pattern fields and two filters.
For anything heavier, write SPARQL.

## 11 · Cypher-lite

Single-pattern Cypher → SPARQL only:

```cypher
MATCH (t:TestCase)-[:validates]->(f:Feature) RETURN t, f
```

Compiles to:

```sparql
SELECT DISTINCT ?t ?f WHERE {
  ?t a cfa:TestCase .
  ?f a cfa:Feature .
  ?t cfa:validates ?f .
} ORDER BY ?t ?f
```

Multi-pattern, WHERE clauses, aggregations, and write operations
(CREATE/MERGE/DELETE) are out of scope — use `--sparql` for those.
