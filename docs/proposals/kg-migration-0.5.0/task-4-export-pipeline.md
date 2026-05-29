# Task 4 — Markdown Export Pipeline Design

> KG Migration 0.5.0 · Agent-T4 produced · grounded in Task 3 (`task-3-domain-ontology.md`) and schema `schemas/core.yaml`.

Anchors:
- Storage: **pyoxigraph 0.5.x** (SPARQL 1.1 via oxrdflib bridge)
- Schema: `docs/proposals/kg-migration-0.5.0/schemas/core.yaml` (LinkML 1.11.x)
- Templating: **Jinja2 3.x** with **Pydantic v2** context objects
- Business namespace: `https://cataforge.dev/ontology/` (`cf:`)
- Instance namespace: `https://cataforge.dev/instance/` (`cfprj:`)
- Default export scope: **business-only** (`KGConfig.governance = false`)

---

## §4.1 Query → Render Conversion Pipeline

### §4.1.1 Pipeline stages

```
KnowledgeGraph (pyoxigraph)
  │
  ▼ [1] SPARQL Query Layer
  │   templates/{entity_type}.sparql  →  raw result rows
  │
  ▼ [2] Hydration Layer
  │   rows  →  Pydantic v2 model instances (LinkML-generated)
  │
  ▼ [3] Jinja2 Render Layer
  │   model instances  +  templates/{doc_type}/{entity_type}.md.j2
  │                    →  raw Markdown strings (per entity)
  │
  ▼ [4] Post-Processing Layer
  │   section numbering, TOC generation, cross-ref resolution,
  │   frontmatter injection  →  final Markdown bytes
  │
  ▼ [5] Write Layer
      deterministic filename  →  docs/{doc_type}/{entity_id}.md
      SHA-256 logged to CompileResult
```

### §4.1.2 SPARQL template registration

Each entity type owns exactly one parameterized SPARQL template file. The registry is a mapping built at startup by scanning the templates directory:

```
cataforge/kg/export/
└── sparql/
    ├── feature.sparql
    ├── module.sparql
    ├── component.sparql
    ├── task.sparql
    ├── testcase.sparql
    ├── testsuite.sparql
    ├── api.sparql
    ├── datamodel.sparql
    ├── acceptancecriteria.sparql
    ├── release.sparql
    ├── deployment.sparql
    ├── pipeline.sparql
    ├── environment.sparql
    ├── architecturedecision.sparql
    ├── risk.sparql
    ├── changerequest.sparql
    ├── reviewreport.sparql
    ├── sprintreviewissue.sparql
    ├── glossary.sparql
    ├── testplan.sparql
    ├── testrun.sparql
    ├── coveragerule.sparql
    ├── page.sparql
    ├── wireframe.sparql
    ├── uicomponent.sparql
    ├── userflow.sparql
    ├── phase.sparql
    ├── sprint.sparql
    ├── iteration.sparql
    └── milestone.sparql
```

Registration convention: filename stem (lowercased, no separator) maps to the LinkML class name. The `SparqlRegistry` scans this directory at process start; plugin-supplied templates from `.cataforge/plugins/<id>/queries/` are merged in afterward (plugin templates may override built-ins for their own entity types only).

```python
# cataforge/kg/export/registry.py
from pathlib import Path
from typing import Dict

_BUILTIN_SPARQL_DIR = Path(__file__).parent / "sparql"

class SparqlRegistry:
    """Maps entity_type (lowercase class name) → SPARQL template string."""

    def __init__(
        self,
        builtin_dir: Path = _BUILTIN_SPARQL_DIR,
        plugin_dirs: list[Path] | None = None,
    ) -> None:
        self._templates: Dict[str, str] = {}
        self._load_dir(builtin_dir)
        for d in (plugin_dirs or []):
            self._load_dir(d, allow_override=True)

    def _load_dir(self, directory: Path, *, allow_override: bool = False) -> None:
        for path in sorted(directory.glob("*.sparql")):
            key = path.stem.lower()
            if key in self._templates and not allow_override:
                raise ValueError(
                    f"Duplicate SPARQL template for '{key}' in {path}. "
                    "Use a plugin directory to override built-in templates."
                )
            self._templates[key] = path.read_text(encoding="utf-8")

    def get(self, entity_type: str) -> str:
        key = entity_type.lower()
        if key not in self._templates:
            raise KeyError(f"No SPARQL template registered for entity type '{entity_type}'")
        return self._templates[key]

    def registered_types(self) -> list[str]:
        return sorted(self._templates)
```

### §4.1.3 Concrete SPARQL templates

**Template A — Feature (Requirement layer)**

Fetches a single Feature by entity_id, with its AcceptanceCriteria, realized Tasks, implementing Modules, and verifying TestCases. The `%(entity_id)s` placeholder is substituted by Python `str % {"entity_id": value}` before execution.

```sparql
# cataforge/kg/export/sparql/feature.sparql
PREFIX cf:    <https://cataforge.dev/ontology/>
PREFIX cfprj: <https://cataforge.dev/instance/>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>

SELECT
  ?feature ?entity_id ?sort_key ?title ?description ?status ?priority
  ?content_hash ?source_doc ?source_section ?authored_by
  ?assigned_to_sprint ?sprint_id
  ?belongs_to_phase ?phase_id
  ?ac ?ac_id ?ac_sort_key ?ac_text
  ?impl ?impl_id ?impl_sort_key ?impl_title ?impl_kind
  ?tc ?tc_id ?tc_sort_key ?tc_title
  ?tag
WHERE {
  ?feature a cf:Feature ;
           cf:entity_id %(entity_id)s ;
           cf:sort_key  ?sort_key ;
           cf:title     ?title .
  BIND(%(entity_id)s AS ?entity_id)

  OPTIONAL { ?feature cf:description  ?description }
  OPTIONAL { ?feature cf:status       ?status }
  OPTIONAL { ?feature cf:priority     ?priority }
  OPTIONAL { ?feature cf:content_hash ?content_hash }
  OPTIONAL { ?feature cf:source_doc   ?source_doc }
  OPTIONAL { ?feature cf:source_section ?source_section }
  OPTIONAL { ?feature cf:authored_by  ?authored_by }
  OPTIONAL { ?feature cf:tags         ?tag }

  OPTIONAL {
    ?feature cf:assigned_to_sprint ?assigned_to_sprint .
    ?assigned_to_sprint cf:entity_id ?sprint_id .
  }
  OPTIONAL {
    ?feature cf:belongs_to_phase ?belongs_to_phase .
    ?belongs_to_phase cf:entity_id ?phase_id .
  }

  OPTIONAL {
    ?ac a cf:AcceptanceCriteria ;
        cf:satisfies ?feature ;
        cf:entity_id ?ac_id ;
        cf:sort_key  ?ac_sort_key ;
        cf:acceptance_text ?ac_text .
  }

  OPTIONAL {
    ?impl cf:implements ?feature ;
          cf:entity_id  ?impl_id ;
          cf:sort_key   ?impl_sort_key ;
          cf:title      ?impl_title ;
          a             ?impl_kind .
    ?impl_kind rdfs:subClassOf* cf:SoftwareArtifact .
  }

  OPTIONAL {
    ?tc a cf:TestCase ;
        cf:verifies+ ?feature ;
        cf:entity_id ?tc_id ;
        cf:sort_key  ?tc_sort_key ;
        cf:title     ?tc_title .
  }
}
ORDER BY ?sort_key ?ac_sort_key ?impl_sort_key ?tc_sort_key
```

**Template B — Module (Architecture layer)**

```sparql
# cataforge/kg/export/sparql/module.sparql
PREFIX cf:    <https://cataforge.dev/ontology/>
PREFIX cfprj: <https://cataforge.dev/instance/>

SELECT
  ?module ?entity_id ?sort_key ?title ?description ?status ?priority
  ?content_hash ?source_doc ?source_section ?authored_by
  ?satisfies_req ?req_id ?req_sort_key ?req_title
  ?task ?task_id ?task_sort_key ?task_title ?task_status
  ?dep ?dep_id ?dep_sort_key ?dep_title
  ?tag
WHERE {
  ?module a cf:Module ;
          cf:entity_id %(entity_id)s ;
          cf:sort_key  ?sort_key ;
          cf:title     ?title .
  BIND(%(entity_id)s AS ?entity_id)

  OPTIONAL { ?module cf:description  ?description }
  OPTIONAL { ?module cf:status       ?status }
  OPTIONAL { ?module cf:priority     ?priority }
  OPTIONAL { ?module cf:content_hash ?content_hash }
  OPTIONAL { ?module cf:source_doc   ?source_doc }
  OPTIONAL { ?module cf:source_section ?source_section }
  OPTIONAL { ?module cf:authored_by  ?authored_by }
  OPTIONAL { ?module cf:tags         ?tag }

  OPTIONAL {
    ?module cf:satisfies ?satisfies_req .
    ?satisfies_req cf:entity_id ?req_id ;
                   cf:sort_key  ?req_sort_key ;
                   cf:title     ?req_title .
  }

  OPTIONAL {
    ?task a cf:Task ;
          cf:realizes ?module ;
          cf:entity_id  ?task_id ;
          cf:sort_key   ?task_sort_key ;
          cf:title      ?task_title ;
          cf:task_status ?task_status .
  }

  OPTIONAL {
    ?module cf:depends_on ?dep .
    ?dep cf:entity_id ?dep_id ;
         cf:sort_key  ?dep_sort_key ;
         cf:title     ?dep_title .
  }
}
ORDER BY ?sort_key ?req_sort_key ?task_sort_key ?dep_sort_key
```

**Template C — TestCase (Test layer)**

```sparql
# cataforge/kg/export/sparql/testcase.sparql
PREFIX cf:    <https://cataforge.dev/ontology/>
PREFIX cfprj: <https://cataforge.dev/instance/>

SELECT
  ?tc ?entity_id ?sort_key ?title ?description ?status
  ?content_hash ?source_doc ?source_section ?authored_by
  ?expected_result ?test_result
  ?step
  ?target ?target_id ?target_sort_key ?target_title ?target_kind
  ?run ?run_id ?run_sort_key ?run_result
  ?tag
WHERE {
  ?tc a cf:TestCase ;
      cf:entity_id %(entity_id)s ;
      cf:sort_key  ?sort_key ;
      cf:title     ?title .
  BIND(%(entity_id)s AS ?entity_id)

  OPTIONAL { ?tc cf:description    ?description }
  OPTIONAL { ?tc cf:status         ?status }
  OPTIONAL { ?tc cf:content_hash   ?content_hash }
  OPTIONAL { ?tc cf:source_doc     ?source_doc }
  OPTIONAL { ?tc cf:source_section ?source_section }
  OPTIONAL { ?tc cf:authored_by    ?authored_by }
  OPTIONAL { ?tc cf:expected_result ?expected_result }
  OPTIONAL { ?tc cf:test_result    ?test_result }
  OPTIONAL { ?tc cf:test_steps     ?step }
  OPTIONAL { ?tc cf:tags           ?tag }

  OPTIONAL {
    ?tc cf:verifies ?target .
    ?target cf:entity_id ?target_id ;
            cf:sort_key  ?target_sort_key ;
            cf:title     ?target_title ;
            a            ?target_kind .
  }

  OPTIONAL {
    ?run a cf:TestRun ;
         cf:verifies  ?tc ;
         cf:entity_id ?run_id ;
         cf:sort_key  ?run_sort_key ;
         cf:test_result ?run_result .
  }
}
ORDER BY ?sort_key ?target_sort_key ?run_sort_key
```

### §4.1.4 Hydration and render steps

After query execution, SPARQL result rows are collapsed into Pydantic model instances (one instance per subject URI, multi-valued slots aggregated). The Pydantic model is then passed as `entity` context to Jinja2. Post-processing runs on the assembled string:

1. Section numbers are injected by a `SectionNumberer` that walks heading levels and maintains a counter stack.
2. Cross-references: URI strings (`cfprj:F-001`) in rendered Markdown are replaced by `[F-001](../prd/F-001.md#F-001)` using the `CrossRefResolver`, which consults a `{entity_id → relative_path}` manifest built during the compile pass.
3. TOC entries are appended to `docs/{doc_type}/_index.md` after all entities of a type are rendered.
4. Frontmatter (YAML block) is injected at the top of each file: `entity_id`, `title`, `status`, `sort_key`, `content_hash`. The `generated_at` field is **excluded** (idempotency requirement).

---

## §4.2 Template Mechanism

### §4.2.1 Template file tree

```
cataforge/kg/export/templates/
├── _base/
│   ├── artifact_base.md.j2        # extends nothing; used by all entities
│   └── relation_list.md.j2        # reusable block: renders a list of related entities
├── prd/
│   ├── feature.md.j2
│   ├── userstory.md.j2
│   └── epic.md.j2
├── arch/
│   ├── module.md.j2
│   ├── component.md.j2
│   ├── api.md.j2
│   ├── datamodel.md.j2
│   └── architecturedecision.md.j2
├── ui-spec/
│   ├── page.md.j2
│   ├── wireframe.md.j2
│   └── uicomponent.md.j2
├── dev-plan/
│   ├── task.md.j2
│   └── subtask.md.j2
├── test-report/
│   ├── testcase.md.j2
│   ├── testsuite.md.j2
│   └── testplan.md.j2
├── deploy-spec/
│   ├── deployment.md.j2
│   ├── release.md.j2
│   └── pipeline.md.j2
└── support/
    ├── glossary.md.j2
    ├── risk.md.j2
    └── reviewreport.md.j2
```

### §4.2.2 Template metadata header

Each `.md.j2` file begins with a YAML front-comment block (Jinja comment, not rendered):

```jinja
{#
  template_format_version: "1"
  schema_version_min: "0.5.0"
  entity_type: Feature
  doc_type: prd
  description: Renders a single Feature entity to prd-style Markdown.
#}
```

`template_format_version` gates compatibility: the exporter reads this value and raises `TemplateVersionError` if the template format version is newer than the engine supports. `schema_version_min` is advisory — the loader emits a warning (not an error) if the loaded schema version is older.

### §4.2.3 Base template and block contract

```jinja
{# cataforge/kg/export/templates/_base/artifact_base.md.j2 #}
---
entity_id: {{ entity.entity_id }}
title: {{ entity.title | tojson }}
status: {{ entity.status | default("draft") }}
sort_key: {{ entity.sort_key }}
content_hash: {{ entity.content_hash | default("") }}
source_doc: {{ entity.source_doc | default("") }}
source_section: {{ entity.source_section | default("") }}
---

{% block heading %}
# {{ entity.entity_id }} — {{ entity.title }}
{% endblock %}

{% block metadata %}
| Field | Value |
|-------|-------|
| Status | `{{ entity.status | default("—") }}` |
| Priority | `{{ entity.priority | default("—") }}` |
| Authored by | {{ entity.authored_by | default("—") }} |
{% if entity.tags %}| Tags | {{ entity.tags | sort | join(", ") }} |{% endif %}
{% endblock %}

{% block description %}
{% if entity.description %}
## Description

{{ entity.description }}
{% endif %}
{% endblock %}

{% block body %}{% endblock %}

{% block relations %}{% endblock %}

{% block source_ref %}
---
*Source: [{{ entity.source_doc | default("—") }}]({{ entity.source_doc | default("#") }}) {{ entity.source_section | default("") }}*
{% endblock %}
```

### §4.2.4 Entity-specific template (Feature example)

```jinja
{#
  template_format_version: "1"
  schema_version_min: "0.5.0"
  entity_type: Feature
  doc_type: prd
#}
{% extends "_base/artifact_base.md.j2" %}

{% block body %}
{% if entity.acceptance_criteria %}
## Acceptance Criteria

{% for ac in entity.acceptance_criteria | sort(attribute="sort_key") %}
- **{{ ac.entity_id }}**: {{ ac.acceptance_text }}
{% endfor %}
{% endif %}

{% if entity.work_unit %}
## Work Assignment

- **{{ entity.work_unit.kind }}**: [{{ entity.work_unit.entity_id }}](../{{ entity.work_unit.entity_id }}.md)
{% endif %}
{% endblock %}

{% block relations %}
{% if entity.implemented_by %}
## Implementation

{% for impl in entity.implemented_by | sort(attribute="sort_key") %}
- [{{ impl.entity_id }}](../arch/{{ impl.entity_id }}.md) — {{ impl.title }}
{% endfor %}
{% endif %}

{% if entity.verified_by %}
## Verification

{% for tc in entity.verified_by | sort(attribute="sort_key") %}
- [{{ tc.entity_id }}](../test-report/{{ tc.entity_id }}.md) — {{ tc.title }}
{% endfor %}
{% endif %}
{% endblock %}
```

### §4.2.5 User-override resolution order

The `TemplateLoader` resolves templates in the following priority order (highest first):

1. `<project_root>/cataforge.templates/{doc_type}/{entity_type}.md.j2` — project-level override
2. `~/.cataforge/templates/{doc_type}/{entity_type}.md.j2` — user-level override (optional)
3. `cataforge/kg/export/templates/{doc_type}/{entity_type}.md.j2` — built-in

```python
# cataforge/kg/export/template_loader.py
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, ChoiceLoader, StrictUndefined

def build_jinja_env(
    project_root: Path,
    builtin_template_dir: Path,
) -> Environment:
    """Construct a Jinja2 Environment respecting the three-tier override order."""
    loaders: list[FileSystemLoader] = []

    project_override = project_root / "cataforge.templates"
    if project_override.is_dir():
        loaders.append(FileSystemLoader(str(project_override)))

    user_override = Path.home() / ".cataforge" / "templates"
    if user_override.is_dir():
        loaders.append(FileSystemLoader(str(user_override)))

    loaders.append(FileSystemLoader(str(builtin_template_dir)))

    env = Environment(
        loader=ChoiceLoader(loaders),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    return env
```

### §4.2.6 Template version × schema version matrix

| template_format_version | Compatible schema versions | Notes |
|------------------------|---------------------------|-------|
| `"1"` | 0.5.x | Initial release; covers all §3.1 entity types |

When a future schema version introduces new mandatory slots, a new `template_format_version: "2"` is declared. The engine keeps the `"1"` templates as fallback for projects that have not yet upgraded their overrides.

---

## §4.3 Diff Functionality

### §4.3.1 Why JSON Lines over unified diff

Unified diff (`git diff` / `diff -u`) operates on textual lines. For Markdown exports, even cosmetic reflows (line-wrapping changes) produce large diffs with no semantic signal. JSON Lines (one JSON object per changed entity) provides:

- **Machine-parseable change events** — downstream tools (CI dashboards, impact analyzers) can filter by change type without parsing diff hunks.
- **Stable entity identity** — each record carries `entity_id` and `sort_key`, decoupled from line position.
- **Relation-level granularity** — a relation-add or relation-remove is a distinct record, not a scattered line change.
- **Streaming output** — the diff can be consumed incrementally as the exporter processes each entity, with no need to hold the entire diff in memory.

Unified diff remains available as a secondary view via `cataforge kg diff --format=unified` for human-readable terminal output, but JSON Lines is the canonical format.

### §4.3.2 JSON Lines diff record schema

Each output line is one JSON object. The `op` field is the change classifier.

```python
# cataforge/kg/export/diff.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional, Any

ChangeOp = Literal[
    "new-entity",
    "modified-entity",
    "deleted-entity",
    "relation-add",
    "relation-remove",
]

@dataclass(frozen=True)
class DiffRecord:
    op: ChangeOp
    entity_type: str        # LinkML class name, e.g. "Feature"
    entity_id: str          # e.g. "F-001"
    sort_key: str           # e.g. "F:000001"
    predicate: Optional[str] = None      # for relation-* ops: e.g. "cf:verifies"
    target_entity_id: Optional[str] = None  # for relation-* ops
    changed_fields: list[str] = field(default_factory=list)
    old_content_hash: Optional[str] = None
    new_content_hash: Optional[str] = None

    def to_jsonl(self) -> str:
        import json
        return json.dumps({
            "op": self.op,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "sort_key": self.sort_key,
            "predicate": self.predicate,
            "target_entity_id": self.target_entity_id,
            "changed_fields": self.changed_fields,
            "old_content_hash": self.old_content_hash,
            "new_content_hash": self.new_content_hash,
        }, ensure_ascii=False)
```

Example output for a relation-add:

```json
{"op": "relation-add", "entity_type": "TestCase", "entity_id": "TC-012", "sort_key": "TC:000012", "predicate": "cf:verifies", "target_entity_id": "F-003", "changed_fields": [], "old_content_hash": null, "new_content_hash": null}
```

### §4.3.3 Change classification rules

| Condition | op |
|-----------|-----|
| `entity_id` present in new export, absent in baseline | `new-entity` |
| `entity_id` absent in new export, present in baseline | `deleted-entity` |
| `content_hash` differs between baseline and new export | `modified-entity` |
| Relation triple present in new graph, absent in baseline graph | `relation-add` |
| Relation triple absent in new graph, present in baseline graph | `relation-remove` |

A `modified-entity` record lists `changed_fields` by diffing the serialized Pydantic model field-by-field. Relations that change also emit their own `relation-add`/`relation-remove` records — the two record types are orthogonal.

### §4.3.4 Git workflow integration

**Standalone `cataforge kg diff` is preferred over a pre-commit hook.**

Rationale:
- A full export + diff over a large graph can take several seconds. Running it on every `git commit` would interrupt the developer's flow and incentivize hook bypasses.
- The exporter is a read-only operation against the KG. Pre-commit hooks are appropriate for fast, stateless checks (lint, format). Graph traversal is neither.
- Diff output belongs in the PR description and CI report, not in a commit-blocking gate.
- Developers may legitimately commit Markdown changes without a full KG re-export (e.g., fixing a typo); the hook would incorrectly flag these as "stale export".

**Recommended workflow:**

```
cataforge kg export --output-dir docs/   # full export, updates all Markdown
cataforge kg diff --baseline-dir docs/   # compare last committed state vs. new export
git add docs/
git commit -m "chore(kg): sync Markdown export from graph"
```

`cataforge kg diff` reads the baseline from `git show HEAD:docs/` (via `subprocess` + `git show`) and the new export from the current working tree. The JSON Lines diff is written to stdout; CI can redirect it to an artifact.

---

## §4.4 Idempotency Guarantee

### §4.4.1 Double-sort guarantee

Byte-identical output across two consecutive exports is guaranteed by applying sort at two independent layers:

1. **SPARQL layer** — every entity-fetch template ends with `ORDER BY ASC(?sort_key)`. Multi-valued relation sub-queries order by `(range.sort_key)` or `(range.entity_id)` where `sort_key` is not available.

2. **Python layer** — after SPARQL result hydration, every multi-valued field on the Pydantic model is re-sorted before template rendering:

```python
# cataforge/kg/export/hydrator.py
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

def stable_sort_relations(entity: T) -> T:
    """
    Re-sort all list-valued fields on a Pydantic model by (sort_key, entity_id).
    This is the Python-side guarantee that SPARQL ORDER BY is not enough:
    SPARQL engines may not preserve stable ordering across joins.
    """
    for field_name, field_info in entity.model_fields.items():
        value = getattr(entity, field_name)
        if not isinstance(value, list):
            continue
        if not value:
            continue
        # Elements are either Pydantic models (with sort_key) or plain strings.
        if hasattr(value[0], "sort_key"):
            sorted_value = sorted(
                value,
                key=lambda x: (
                    getattr(x, "sort_key", ""),
                    getattr(x, "entity_id", ""),
                ),
            )
        else:
            sorted_value = sorted(str(v) for v in value)
        object.__setattr__(entity, field_name, sorted_value)
    return entity
```

### §4.4.2 Multi-valued relation sort key

For relations where both endpoints carry `sort_key`, the sort key for the relation list entry is the tuple `(range.sort_key, range.entity_id)` compared lexicographically. This gives a deterministic order even if two entities share a `sort_key` prefix (which the schema forbids, but the exporter treats defensively).

### §4.4.3 `generated_at` suppression

`generated_at` is computed during export for operational logging (written to `CompileResult.exported_at`) but is **never written into any Markdown output file or YAML frontmatter**. The Jinja2 base template does not include a `generated_at` variable. Template authors who add `{{ generated_at }}` to an override template will receive a `jinja2.UndefinedError` (the environment uses `StrictUndefined`), making the omission explicit.

### §4.4.4 Reification node IDs from content hash

TraceabilityLink nodes (if introduced in future schema extensions) derive their URI from a SHA-256 of the canonical triple `(subject_entity_id, predicate_curie, object_entity_id)`, encoded as UTF-8 JSON:

```python
import hashlib, json

def reification_node_id(
    subject_entity_id: str,
    predicate: str,
    object_entity_id: str,
) -> str:
    """
    Deterministic URI fragment for a reification node.
    Two identical triples always produce the same ID; UUID is never used.
    """
    canonical = json.dumps(
        [subject_entity_id, predicate, object_entity_id],
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"link-{digest}"
```

### §4.4.5 Idempotency test plan

```python
# tests/kg/test_export_idempotency.py
import hashlib
from pathlib import Path
from typing import Dict

def sha256_dir(directory: Path) -> Dict[str, str]:
    """Return {relative_path: sha256_hex} for every file under directory."""
    result: Dict[str, str] = {}
    for path in sorted(directory.rglob("*.md")):
        data = path.read_bytes()
        result[str(path.relative_to(directory))] = hashlib.sha256(data).hexdigest()
    return result

def test_export_idempotency(tmp_path, populated_graph):
    """Two consecutive compile_to_markdown() calls must produce byte-identical output."""
    from cataforge.domain.kg.export.pipeline import compile_to_markdown

    out1 = tmp_path / "export1"
    out2 = tmp_path / "export2"
    out1.mkdir(); out2.mkdir()

    result1 = compile_to_markdown(graph=populated_graph, output_dir=out1)
    result2 = compile_to_markdown(graph=populated_graph, output_dir=out2)

    hashes1 = sha256_dir(out1)
    hashes2 = sha256_dir(out2)

    assert hashes1.keys() == hashes2.keys(), (
        f"File sets differ: {hashes1.keys() ^ hashes2.keys()}"
    )
    for rel_path in hashes1:
        assert hashes1[rel_path] == hashes2[rel_path], (
            f"SHA-256 mismatch for '{rel_path}': "
            f"{hashes1[rel_path]} != {hashes2[rel_path]}"
        )

    # CompileResult also exposes per-file hashes for CI artifact logging.
    assert result1.file_hashes == result2.file_hashes
```

The `populated_graph` fixture loads the Turtle fragment from Task 3 §3.7.3 into a fresh pyoxigraph store. The test is parameterized over: (a) full export with no filter, (b) export filtered to `entity_type="Feature"`, (c) export after a no-op incremental pass.

---

## §4.5 Incremental Export

### §4.5.1 Snapshot and change detection

Each full export writes a **snapshot manifest** to `docs/.kg-export-snapshot.json`:

```json
{
  "schema_version": "0.5.0",
  "snapshot_type": "full",
  "entities": {
    "F-001": {"content_hash": "9f3aab12", "sort_key": "F:000001", "output_path": "prd/F-001.md"},
    "M-014": {"content_hash": "7c81de44", "sort_key": "M:000014", "output_path": "arch/M-014.md"}
  }
}
```

An incremental export compares each entity's current `cf:content_hash` from the graph against the snapshot. Entities where `graph_hash != snapshot_hash` (or that are absent from the snapshot) are marked **dirty**.

### §4.5.2 Downstream propagation via reverse-traversal

After identifying dirty entities, the exporter reverse-traverses traceability relations to find **affected downstream** entities whose Markdown documents reference the dirty entity via cross-references:

```python
DOWNSTREAM_PREDICATES = [
    "cf:verifies",       # TestCase → Feature (export TestCase if Feature changed)
    "cf:implements",     # Module → Feature
    "cf:satisfies",      # Component/Page → Requirement
    "cf:delivers",       # Release → Feature
    "cf:affects",        # ChangeRequest → any
    "cf:realized_as",    # Module → Task
]

def find_affected_entities(
    dirty_ids: set[str],
    graph: "KnowledgeGraphProtocol",
) -> set[str]:
    """
    Return the closure of entity_ids whose Markdown output may reference
    any dirty entity. Uses one SPARQL query per predicate direction.
    """
    affected: set[str] = set(dirty_ids)
    for predicate in DOWNSTREAM_PREDICATES:
        sparql = f"""
        PREFIX cf: <https://cataforge.dev/ontology/>
        SELECT DISTINCT ?referrer_id WHERE {{
            ?referrer {predicate} ?target .
            ?target cf:entity_id ?dirty_id .
            ?referrer cf:entity_id ?referrer_id .
            FILTER(?dirty_id IN ({", ".join(f'"{i}"' for i in dirty_ids)}))
        }}
        """
        for row in graph.query(sparql):
            affected.add(str(row["referrer_id"]))
    return affected
```

### §4.5.3 Consistency guarantee

**N incremental exports == 1 full export** (same final Markdown state).

This is guaranteed by the following invariant: an incremental export always re-renders both the dirty entity and all entities that reference it. Because every cross-reference in rendered Markdown is resolved from the current graph state (not the snapshot), the output of an incremental export for the affected set is byte-identical to what a full export would produce for those same files.

Proof sketch:
- Let S₀ be the graph state at last full export.
- Let S₁ = S₀ + {dirty changes}.
- Full export on S₁ → F(S₁).
- Incremental export on S₁: identifies dirty set D; renders affected set A ⊇ D; for files not in A, copies from S₀ output unchanged.
- For any file f ∈ A: `render(S₁, f)` == `F(S₁)[f]` because both use identical SPARQL + sort + template.
- For any file f ∉ A: f's Markdown contains no cross-reference to any entity in D (by definition of A), so `F(S₀)[f]` == `F(S₁)[f]`.

The snapshot is updated after each incremental export to reflect the new hashes.

---

## §4.6 Core Conversion Function Interface

### §4.6.1 Protocol and supporting types

```python
# cataforge/kg/export/types.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Iterator, Optional, Any


class KnowledgeGraphProtocol(Protocol):
    """
    Minimal interface that the export pipeline requires from any graph backend.

    The concrete implementation wraps pyoxigraph 0.5.x (via oxrdflib).
    A stub implementation is sufficient for unit-testing the pipeline.
    """

    def query(self, sparql: str) -> Iterator[dict[str, Any]]:
        """
        Execute a SPARQL SELECT query and yield result rows as dicts.

        Args:
            sparql: A valid SPARQL 1.1 SELECT query string.

        Yields:
            One dict per result row mapping variable name (str) → value.
            Literal values are yielded as Python scalars (str/int/float/bool).
            URI values are yielded as str in the form "<namespace><local>".

        Raises:
            SparqlSyntaxError: If the query string is malformed.
            GraphQueryError: If the backend raises a retrieval error.
        """
        ...

    def entity_hash(self, entity_id: str) -> Optional[str]:
        """
        Return the current cf:content_hash for entity_id, or None if absent.

        Args:
            entity_id: Frontmatter ID such as "F-001" or "TC-007".

        Returns:
            SHA-256 hex string, or None if the entity is not in the graph.
        """
        ...

    def entity_count(self) -> int:
        """Return the total number of SoftwareArtifact instances in the graph."""
        ...


@dataclass(frozen=True)
class EntityFilter:
    """
    Restricts which entities are exported in a compile_to_markdown() call.

    All fields are optional; omitting a field means "no restriction" for
    that dimension. Multiple fields are ANDed together.

    Attributes:
        entity_types: If non-empty, only export entities whose LinkML class
            name is in this set (e.g. {"Feature", "Module"}).
        entity_ids: If non-empty, only export the listed entity_ids
            (e.g. {"F-001", "F-002"}).
        doc_types: If non-empty, only export entities whose associated
            doc_type (prd, arch, test-report, etc.) is in this set.
        status_values: If non-empty, only export entities whose cf:status
            is one of the listed ArtifactStatusEnum values.
        changed_only: If True, skip entities whose content_hash matches the
            snapshot manifest (used internally by incremental export).

    Example:
        EntityFilter(entity_types={"Feature", "AcceptanceCriteria"})
        # exports only Requirement-layer entities
    """

    entity_types: frozenset[str] = field(default_factory=frozenset)
    entity_ids: frozenset[str] = field(default_factory=frozenset)
    doc_types: frozenset[str] = field(default_factory=frozenset)
    status_values: frozenset[str] = field(default_factory=frozenset)
    changed_only: bool = False

    def matches(self, entity_type: str, entity_id: str, doc_type: str, status: str) -> bool:
        """
        Return True if this entity passes all active filter dimensions.

        Args:
            entity_type: LinkML class name.
            entity_id: Frontmatter ID.
            doc_type: Document type bucket (prd, arch, etc.).
            status: ArtifactStatusEnum value string.

        Returns:
            True if the entity should be included in the export.
        """
        if self.entity_types and entity_type not in self.entity_types:
            return False
        if self.entity_ids and entity_id not in self.entity_ids:
            return False
        if self.doc_types and doc_type not in self.doc_types:
            return False
        if self.status_values and status not in self.status_values:
            return False
        return True


@dataclass
class FileExportRecord:
    """
    Record for a single exported Markdown file.

    Attributes:
        entity_id: The entity's frontmatter ID.
        entity_type: LinkML class name.
        output_path: Absolute path to the written file.
        sha256: SHA-256 hex of the file content as written.
        from_cache: True if the file was copied from the snapshot without re-rendering.
    """

    entity_id: str
    entity_type: str
    output_path: Path
    sha256: str
    from_cache: bool = False


@dataclass
class CompileResult:
    """
    Return value of compile_to_markdown().

    Attributes:
        exported_at: UTC timestamp of the export run (NOT written into any file).
        entity_count: Total number of entities processed (filtered + rendered + cached).
        rendered_count: Number of entities actually re-rendered (excludes cache hits).
        output_dir: The root directory that received exported files.
        file_records: One FileExportRecord per output file, sorted by sort_key.
        file_hashes: Convenience mapping {relative_output_path: sha256} for
            idempotency assertions and snapshot manifests.
        errors: List of (entity_id, error_message) for entities that failed to
            export. A non-empty errors list means the export is partial.
        snapshot_path: Path to the written snapshot manifest, or None if the
            export was filtered (partial exports do not update the snapshot).

    Usage:
        result = compile_to_markdown(graph, output_dir=Path("docs"))
        if result.errors:
            for entity_id, msg in result.errors:
                logger.error("Export failed for %s: %s", entity_id, msg)
        print(f"Rendered {result.rendered_count}/{result.entity_count} entities")
    """

    exported_at: datetime
    entity_count: int
    rendered_count: int
    output_dir: Path
    file_records: list[FileExportRecord] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)
    errors: list[tuple[str, str]] = field(default_factory=list)
    snapshot_path: Optional[Path] = None
```

### §4.6.2 Main entry point

```python
# cataforge/kg/export/pipeline.py
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cataforge.domain.kg.export.types import (
    CompileResult,
    EntityFilter,
    FileExportRecord,
    KnowledgeGraphProtocol,
)
from cataforge.domain.kg.export.registry import SparqlRegistry
from cataforge.domain.kg.export.hydrator import hydrate_entity, stable_sort_relations
from cataforge.domain.kg.export.template_loader import build_jinja_env
from cataforge.domain.kg.export.postprocess import PostProcessor
from cataforge.domain.kg.export.snapshot import SnapshotManager

logger = logging.getLogger(__name__)

_BUILTIN_TEMPLATE_DIR = Path(__file__).parent / "templates"
_BUILTIN_SPARQL_DIR = Path(__file__).parent / "sparql"


def compile_to_markdown(
    graph: KnowledgeGraphProtocol,
    entity_filter: Optional[EntityFilter] = None,
    template_override: Optional[Path] = None,
    output_dir: Path = Path("./docs"),
) -> CompileResult:
    """
    Export all (or filtered) entities from the knowledge graph to Markdown files.

    The export is **byte-identical idempotent**: two consecutive calls with an
    unchanged graph produce files with identical SHA-256 hashes.

    Idempotency is guaranteed by:
    1. SPARQL ORDER BY ?sort_key in every entity-fetch template.
    2. Python-side stable re-sort of all multi-valued model fields.
    3. Suppression of ``generated_at`` from all Markdown output.
    4. Jinja2 StrictUndefined to catch accidental timestamp injection.

    Args:
        graph: Any object satisfying KnowledgeGraphProtocol.  The concrete
            production implementation wraps pyoxigraph 0.5.x via oxrdflib.
        entity_filter: If provided, only entities passing the filter are
            exported.  A None filter exports every SoftwareArtifact in the
            graph.  Filtered exports do NOT update the snapshot manifest.
        template_override: If provided, this directory is searched first for
            Jinja2 templates, before project-level and built-in locations.
            Useful for one-off custom renders without editing settings.
        output_dir: Root directory for Markdown output.  Sub-directories
            (``prd/``, ``arch/``, ``test-report/``, etc.) are created as
            needed.  Existing files are overwritten; no files are deleted.

    Returns:
        CompileResult containing per-file SHA-256 hashes, error list, and
        a reference to the written snapshot manifest path.

    Raises:
        OutputDirError: If output_dir cannot be created or written.
        TemplateVersionError: If a template's template_format_version is
            newer than the engine supports.
        ValueError: If entity_filter references unknown entity types.

    Notes:
        - Async variant ``acompile_to_markdown()`` is NOT provided.  The
          pyoxigraph SPARQL engine is synchronous; the bottleneck is graph
          traversal, not I/O.  Introducing async here would add coroutine
          overhead without parallelism benefit, since pyoxigraph holds a
          write lock during queries.  If concurrent export is needed, run
          multiple processes against read-only snapshots.
        - ``generated_at`` is recorded in CompileResult.exported_at but is
          never written into any Markdown file or YAML frontmatter block.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    entity_filter = entity_filter or EntityFilter()
    exported_at = datetime.now(timezone.utc)

    registry = SparqlRegistry(builtin_dir=_BUILTIN_SPARQL_DIR)

    extra_dirs: list[Path] = []
    if template_override:
        extra_dirs.append(template_override)
    jinja_env = build_jinja_env(
        project_root=output_dir.parent,
        builtin_template_dir=_BUILTIN_TEMPLATE_DIR,
    )

    snapshot_mgr = SnapshotManager(output_dir)
    snapshot = snapshot_mgr.load()

    post = PostProcessor()

    file_records: list[FileExportRecord] = []
    errors: list[tuple[str, str]] = []

    # Step 1: Enumerate all SoftwareArtifact instances, sorted by sort_key.
    entity_list_sparql = """
    PREFIX cf:   <https://cataforge.dev/ontology/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?entity_id ?sort_key ?entity_type WHERE {
        ?artifact a ?cls ;
                  cf:entity_id ?entity_id ;
                  cf:sort_key  ?sort_key .
        ?cls rdfs:subClassOf* cf:SoftwareArtifact .
        BIND(STRAFTER(STR(?cls), "https://cataforge.dev/ontology/") AS ?entity_type)
    }
    ORDER BY ASC(?sort_key)
    """
    entity_rows = list(graph.query(entity_list_sparql))

    # Step 2: Apply filter and detect changed entities.
    to_export: list[dict] = []
    for row in entity_rows:
        eid = str(row["entity_id"])
        etype = str(row["entity_type"])
        doc_type = _entity_type_to_doc_type(etype)
        status = ""  # resolved per-entity during hydration if filter needs it
        if not entity_filter.matches(etype, eid, doc_type, status):
            continue
        if entity_filter.changed_only:
            graph_hash = graph.entity_hash(eid)
            snap_hash = snapshot.get(eid, {}).get("content_hash")
            if graph_hash == snap_hash:
                continue
        to_export.append(row)

    # Step 3: Render each entity.
    for row in to_export:
        eid = str(row["entity_id"])
        etype = str(row["entity_type"])
        sort_key = str(row["sort_key"])

        try:
            template_name = _entity_type_to_template_path(etype)
            sparql_template = registry.get(etype)
            sparql_query = sparql_template % {"entity_id": f'"{eid}"'}

            raw_rows = list(graph.query(sparql_query))
            model = hydrate_entity(etype, raw_rows)
            model = stable_sort_relations(model)

            template = jinja_env.get_template(template_name)
            rendered = template.render(entity=model)
            rendered = post.process(rendered, entity_id=eid, entity_type=etype)

            doc_type = _entity_type_to_doc_type(etype)
            out_file = output_dir / doc_type / f"{eid}.md"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            content_bytes = rendered.encode("utf-8")
            out_file.write_bytes(content_bytes)

            sha = hashlib.sha256(content_bytes).hexdigest()
            file_records.append(
                FileExportRecord(
                    entity_id=eid,
                    entity_type=etype,
                    output_path=out_file,
                    sha256=sha,
                )
            )
            logger.debug("Exported %s (%s) → %s", eid, sort_key, out_file)

        except Exception as exc:
            logger.error("Failed to export entity '%s': %s", eid, exc)
            errors.append((eid, str(exc)))

    # Step 4: Write snapshot manifest (only for full, unfiltered exports).
    snapshot_path: Optional[Path] = None
    is_full_export = (
        not entity_filter.entity_types
        and not entity_filter.entity_ids
        and not entity_filter.doc_types
        and not entity_filter.status_values
    )
    if is_full_export and not errors:
        snapshot_path = snapshot_mgr.write(file_records)

    file_hashes = {
        str(r.output_path.relative_to(output_dir)): r.sha256
        for r in file_records
    }

    return CompileResult(
        exported_at=exported_at,
        entity_count=len(to_export),
        rendered_count=len(file_records),
        output_dir=output_dir,
        file_records=sorted(file_records, key=lambda r: r.entity_id),
        file_hashes=file_hashes,
        errors=errors,
        snapshot_path=snapshot_path,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ENTITY_TYPE_TO_DOC_TYPE: dict[str, str] = {
    "Feature": "prd",
    "UserStory": "prd",
    "Epic": "prd",
    "AcceptanceCriteria": "prd",
    "Module": "arch",
    "Component": "arch",
    "Interface": "arch",
    "API": "arch",
    "DataModel": "arch",
    "ArchitectureDecision": "arch",
    "Page": "ui-spec",
    "Screen": "ui-spec",
    "Wireframe": "ui-spec",
    "UIComponent": "ui-spec",
    "UserFlow": "ui-spec",
    "Task": "dev-plan",
    "Subtask": "dev-plan",
    "Phase": "dev-plan",
    "Sprint": "dev-plan",
    "Iteration": "dev-plan",
    "Milestone": "dev-plan",
    "TestCase": "test-report",
    "TestSuite": "test-report",
    "TestPlan": "test-report",
    "TestRun": "test-report",
    "CoverageRule": "test-report",
    "Deployment": "deploy-spec",
    "Pipeline": "deploy-spec",
    "Release": "deploy-spec",
    "Environment": "deploy-spec",
    "Glossary": "support",
    "Risk": "support",
    "ChangeRequest": "support",
    "ReviewReport": "support",
    "SprintReviewIssue": "support",
}


def _entity_type_to_doc_type(entity_type: str) -> str:
    return _ENTITY_TYPE_TO_DOC_TYPE.get(entity_type, "misc")


def _entity_type_to_template_path(entity_type: str) -> str:
    doc_type = _entity_type_to_doc_type(entity_type)
    return f"{doc_type}/{entity_type.lower()}.md.j2"
```

### §4.6.3 Sync vs. async decision

`compile_to_markdown()` is **synchronous**. The primary bottleneck is pyoxigraph SPARQL traversal, which:

- Uses a C-extension SPARQL engine internally — there is no Python-level I/O suspension point to benefit from `await`.
- Holds a read transaction for the duration of the query; async would not parallelize concurrent queries within one export run.
- Writes output files sequentially (ordered by `sort_key`) to preserve deterministic output — parallel file writes would require post-sort merge and add complexity with no throughput benefit for typical project sizes (hundreds to low-thousands of entities).

An `acompile_to_markdown()` wrapper is not provided. If callers need to run an export without blocking an event loop, they should use `asyncio.to_thread(compile_to_markdown, ...)` from the caller side. This keeps the export pipeline free of async machinery and makes it straightforwardly testable with `pytest` (no `pytest-asyncio` required).

---

## [依赖传递摘要]

**关键决策**：

- **SPARQL 模板注册机制**：`cataforge/kg/export/sparql/{entity_type}.sparql` 文件约定，`SparqlRegistry` 扫描加载。Task 6（KG 写入侧）和插件开发者需遵循同一目录约定添加模板；插件模板放 `.cataforge/plugins/<id>/queries/`，允许覆盖同名内建模板。
- **幂等性双重保障**：SPARQL `ORDER BY ?sort_key` + Python 侧 `stable_sort_relations()` 对所有多值字段重排，缺一不可。Task 5（SHACL 验证）需确保每个 `cf:SoftwareArtifact` 子类实例都携带合法 `sort_key`；如 `sort_key` 缺失，幂等性保障失效。
- **`generated_at` 从不写入 Markdown**：通过 `StrictUndefined` 在 Jinja2 层强制保障，CompileResult.exported_at 仅用于运维日志。下游 Task 6 文档写入侧同样禁止注入时间戳。
- **同步 API**：`compile_to_markdown()` 为同步函数，依赖方无需 asyncio 环境，`pytest` 可直接调用。
- **diff 输出格式**：JSON Lines（`DiffRecord`），非 unified diff。Task 6 CI 集成、PR 审核工具应消费 JSON Lines 格式而非解析文本 diff。
- **增量导出一致性**：N 次增量 == 1 次全量，通过 `SnapshotManager` + `content_hash` 比对 + 反向关系传播保障；Task 5 的 `content_hash` 写入正确性是前提。
- **模板三级覆盖顺序**：project `cataforge.templates/` > user `~/.cataforge/templates/` > 内建。下游项目可在 `cataforge.templates/` 定制输出格式，无需 fork 框架。

**输出物路径/位置**：

- `docs/proposals/kg-migration-0.5.0/task-4-export-pipeline.md`（本文档）

设计所描述的实现文件路径（待 Task 6/实施阶段落地）：

- `cataforge/kg/export/pipeline.py` — `compile_to_markdown()` 主入口
- `cataforge/kg/export/types.py` — `EntityFilter` / `CompileResult` / `KnowledgeGraphProtocol`
- `cataforge/kg/export/registry.py` — `SparqlRegistry`
- `cataforge/kg/export/hydrator.py` — `hydrate_entity()` / `stable_sort_relations()`
- `cataforge/kg/export/template_loader.py` — `build_jinja_env()`
- `cataforge/kg/export/postprocess.py` — `PostProcessor`
- `cataforge/kg/export/snapshot.py` — `SnapshotManager`
- `cataforge/kg/export/diff.py` — `DiffRecord`
- `cataforge/kg/export/sparql/*.sparql` — 每实体类型一个 SPARQL 模板
- `cataforge/kg/export/templates/**/*.md.j2` — Jinja2 模板树
- `tests/kg/test_export_idempotency.py` — 幂等性测试

**阻塞标记**：NONE。以下为下游需验证项（非阻塞）：

- Task 5 需确认 pyoxigraph SPARQL property path `a/rdfs:subClassOf*` 在 0.5.x 版本的行为（§4.6.2 实体枚举查询依赖此语法）。
- Task 5 需验证 `cf:content_hash` 写入流程的正确性，因增量导出的一致性依赖此字段。
