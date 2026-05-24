"""``cataforge kg adapter-migrate`` — batch-inject ``kg_adapter`` blocks.

Design §3.5: each authoring agent / read-only agent / doc skill gets a
single ``kg_adapter`` frontmatter block declaring which built-in adapter
handles its dispatch and what SPARQL / schema config feeds it. Doing this
by hand across 24 files is error-prone; doing it via a single tool keeps
the prompt-asset diffs minimal and reviewable.

The migration is idempotent: when a target already carries a
``kg_adapter`` block, the tool leaves it alone unless ``--force`` is
passed. Schema files (one per authoring adapter) are written into
``.cataforge/skills/<skill>/schemas/`` only when missing — the user is
free to refine the canonical mapping post-migration without worrying
that a re-run will overwrite it."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from cataforge.kg.adapters import get as get_adapter


class AdapterMigrationError(RuntimeError):
    """Raised on manifest / target-file / schema authoring failures."""


@dataclass(frozen=True)
class TargetAssignment:
    """One agent or skill that should carry a ``kg_adapter`` block.

    ``target`` is the project-relative path to the AGENT.md / SKILL.md.
    ``adapter`` is the registered adapter name. ``config`` is the
    canonical config block (will be merged into the kg_adapter block).
    ``schema_path`` and ``schema_body`` together describe an optional
    JSON Schema written alongside the prompt asset; if either is None
    no schema is materialised."""

    target: str
    adapter: str
    config: dict[str, Any]
    schema_path: str | None = None
    schema_body: dict[str, Any] | None = None


@dataclass
class MigrationReport:
    """Outcome of a :func:`migrate_adapters` invocation."""

    frontmatter_written: list[Path] = field(default_factory=list)
    frontmatter_skipped: list[Path] = field(default_factory=list)
    schemas_written: list[Path] = field(default_factory=list)
    schemas_skipped: list[Path] = field(default_factory=list)
    targets_missing: list[Path] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return len(self.frontmatter_written) + len(self.schemas_written)

    def format(self) -> str:
        lines = [
            f"frontmatter written  : {len(self.frontmatter_written)}",
            f"frontmatter skipped  : {len(self.frontmatter_skipped)}",
            f"schemas written      : {len(self.schemas_written)}",
            f"schemas skipped      : {len(self.schemas_skipped)}",
        ]
        if self.targets_missing:
            lines.append(
                f"targets missing      : {len(self.targets_missing)}",
            )
            for p in self.targets_missing:
                lines.append(f"  - {p}")
        return "\n".join(lines)


# ---------- canonical SPARQL fragments ----------

_PRE_FEATURES_IN_DOC = (
    "SELECT ?id ?label WHERE {\n"
    "  ?f a cfa:Feature ; cfk:hasId ?id ; rdfs:label ?label ;\n"
    "     cfk:definedIn $doc_iri .\n"
    "} ORDER BY ?id"
)

_PRE_MODULES_IN_DOC = (
    "SELECT ?id ?label WHERE {\n"
    "  ?m a cfa:Module ; cfk:hasId ?id ; rdfs:label ?label ;\n"
    "     cfk:definedIn $doc_iri .\n"
    "} ORDER BY ?id"
)

_PRE_TASKS_IN_DOC = (
    "SELECT ?id ?label WHERE {\n"
    "  ?t a cfa:Task ; cfk:hasId ?id ; rdfs:label ?label ;\n"
    "     cfk:definedIn $doc_iri .\n"
    "} ORDER BY ?id"
)

_PRE_TESTS_IN_DOC = (
    "SELECT ?id WHERE {\n"
    "  ?t a cfa:TestCase ; cfk:hasId ?id ;\n"
    "     cfk:definedIn $doc_iri .\n"
    "} ORDER BY ?id"
)

_PRE_COMPONENTS_IN_DOC = (
    "SELECT ?id ?label WHERE {\n"
    "  ?c a cfa:Component ; cfk:hasId ?id ; rdfs:label ?label ;\n"
    "     cfk:definedIn $doc_iri .\n"
    "} ORDER BY ?id"
)

_PRE_DOC_SUMMARY = (
    "SELECT ?label WHERE {\n"
    "  $doc_iri rdfs:label ?label .\n"
    "} LIMIT 1"
)


# ---------- canonical write-back schemas ----------

_FEATURE_SCHEMA: dict[str, Any] = {
    "$comment": (
        "feature_authoring write-back schema — agent emits "
        "{doc_id, doc_iri, features: [{id, label, status?}]}"
    ),
    "items": [{
        "from": "features",
        "iri": "cfa:${doc_id}/${id}",
        "type": "cfa:Feature",
        "literals": {
            "cfk:hasId": "id",
            "rdfs:label": "label",
            "cfa:status": {"field": "status", "optional": True},
        },
        "iri_refs": {
            "cfk:definedIn": "cfk:doc/${doc_id}",
        },
    }],
}

_MODULE_SCHEMA: dict[str, Any] = {
    "$comment": (
        "module_implements write-back — agent emits "
        "{doc_id, doc_iri, modules: [{id, label, implements: [iri,...]}]}"
    ),
    "items": [{
        "from": "modules",
        "iri": "cfa:${doc_id}/${id}",
        "type": "cfa:Module",
        "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
        "iri_refs": {
            "cfk:definedIn": "cfk:doc/${doc_id}",
            "cfa:implements": {"field": "implements", "as_iri": True},
        },
    }],
}

_TASK_SCHEMA: dict[str, Any] = {
    "$comment": "task_decompose write-back",
    "items": [{
        "from": "tasks",
        "iri": "cfa:${doc_id}/${id}",
        "type": "cfa:Task",
        "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
        "iri_refs": {
            "cfk:definedIn": "cfk:doc/${doc_id}",
            "cfa:decomposes": {"field": "decomposes", "as_iri": True},
        },
    }],
}

_TEST_SCHEMA: dict[str, Any] = {
    "$comment": "test_validates write-back",
    "items": [{
        "from": "test_cases",
        "iri": "cfa:${doc_id}/${id}",
        "type": "cfa:TestCase",
        "literals": {"cfk:hasId": "id"},
        "iri_refs": {
            "cfk:definedIn": "cfk:doc/${doc_id}",
            "cfa:validates": {"field": "validates", "as_iri": True},
        },
    }],
}

_COMPONENT_SCHEMA: dict[str, Any] = {
    "$comment": "ui_renders write-back",
    "items": [{
        "from": "components",
        "iri": "cfa:${doc_id}/${id}",
        "type": "cfa:Component",
        "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
        "iri_refs": {
            "cfk:definedIn": "cfk:doc/${doc_id}",
            "cfa:renders": {"field": "renders", "as_iri": True},
        },
    }],
}


# ---------- canonical config templates ----------

def _doc_read_config(extras: dict[str, str] | None = None) -> dict[str, Any]:
    queries = {"doc_summary": _PRE_DOC_SUMMARY}
    if extras:
        queries.update(extras)
    return {
        "doc_id_param": "doc_id",
        "pre_dispatch_queries": queries,
    }


def _feature_authoring_config(schema_rel: str) -> dict[str, Any]:
    return {
        "doc_id_param": "doc_id",
        "pre_dispatch_queries": {
            "existing_features": _PRE_FEATURES_IN_DOC,
        },
        "write_back_schema": schema_rel,
    }


def _module_implements_config(schema_rel: str) -> dict[str, Any]:
    return {
        "doc_id_param": "doc_id",
        "upstream_doc_param": "prd_doc_iri",
        "pre_dispatch_queries": {
            "upstream_features": _PRE_FEATURES_IN_DOC,
            "existing_modules": _PRE_MODULES_IN_DOC,
        },
        "write_back_schema": schema_rel,
    }


def _task_decompose_config(schema_rel: str) -> dict[str, Any]:
    return {
        "doc_id_param": "doc_id",
        "upstream_doc_param": "arch_doc_iri",
        "pre_dispatch_queries": {
            "upstream_modules": _PRE_MODULES_IN_DOC,
            "existing_tasks": _PRE_TASKS_IN_DOC,
        },
        "write_back_schema": schema_rel,
    }


def _test_validates_config(schema_rel: str) -> dict[str, Any]:
    return {
        "doc_id_param": "doc_id",
        "upstream_doc_param": "prd_doc_iri",
        "pre_dispatch_queries": {
            "features_to_cover": _PRE_FEATURES_IN_DOC,
            "existing_tests": _PRE_TESTS_IN_DOC,
        },
        "write_back_schema": schema_rel,
    }


def _ui_renders_config(schema_rel: str) -> dict[str, Any]:
    return {
        "doc_id_param": "doc_id",
        "upstream_doc_param": "prd_doc_iri",
        "pre_dispatch_queries": {
            "features_to_render": _PRE_FEATURES_IN_DOC,
            "existing_components": _PRE_COMPONENTS_IN_DOC,
        },
        "write_back_schema": schema_rel,
    }


# ---------- migration plan ----------

def _schema_rel(skill: str, name: str) -> str:
    return f".cataforge/skills/{skill}/schemas/{name}.schema.json"


def default_plan() -> list[TargetAssignment]:
    """The canonical 24-target migration plan (design §3.5).

    Updates here propagate to every dogfood / downstream project the next
    time they run ``cataforge kg adapter-migrate``; keep the diff small
    and well-justified."""
    plans: list[TargetAssignment] = []

    # ---- Read-only agents (4) ----
    for agent in ("reviewer", "reflector", "debugger", "qa-engineer"):
        plans.append(TargetAssignment(
            target=f".cataforge/agents/{agent}/AGENT.md",
            adapter="doc_read",
            config=_doc_read_config(),
        ))

    # ---- Authoring agents (5) ----
    plans.append(TargetAssignment(
        target=".cataforge/agents/product-manager/AGENT.md",
        adapter="feature_authoring",
        config=_feature_authoring_config(_schema_rel("doc-gen", "feature")),
        schema_path=_schema_rel("doc-gen", "feature"),
        schema_body=_FEATURE_SCHEMA,
    ))
    plans.append(TargetAssignment(
        target=".cataforge/agents/architect/AGENT.md",
        adapter="module_implements",
        config=_module_implements_config(_schema_rel("doc-gen", "module")),
        schema_path=_schema_rel("doc-gen", "module"),
        schema_body=_MODULE_SCHEMA,
    ))
    plans.append(TargetAssignment(
        target=".cataforge/agents/tech-lead/AGENT.md",
        adapter="task_decompose",
        config=_task_decompose_config(_schema_rel("doc-gen", "task")),
        schema_path=_schema_rel("doc-gen", "task"),
        schema_body=_TASK_SCHEMA,
    ))
    plans.append(TargetAssignment(
        target=".cataforge/agents/ui-designer/AGENT.md",
        adapter="ui_renders",
        config=_ui_renders_config(_schema_rel("doc-gen", "component")),
        schema_path=_schema_rel("doc-gen", "component"),
        schema_body=_COMPONENT_SCHEMA,
    ))
    plans.append(TargetAssignment(
        target=".cataforge/agents/test-writer/AGENT.md",
        adapter="test_validates",
        config=_test_validates_config(_schema_rel("doc-gen", "test")),
        schema_path=_schema_rel("doc-gen", "test"),
        schema_body=_TEST_SCHEMA,
    ))

    # ---- Doc / authoring skills (6) ----
    plans.append(TargetAssignment(
        target=".cataforge/skills/doc-gen/SKILL.md",
        adapter="feature_authoring",
        config=_feature_authoring_config(_schema_rel("doc-gen", "feature")),
    ))
    plans.append(TargetAssignment(
        target=".cataforge/skills/req-analysis/SKILL.md",
        adapter="feature_authoring",
        config=_feature_authoring_config(_schema_rel("doc-gen", "feature")),
    ))
    plans.append(TargetAssignment(
        target=".cataforge/skills/arc-design/SKILL.md",
        adapter="module_implements",
        config=_module_implements_config(_schema_rel("doc-gen", "module")),
    ))
    plans.append(TargetAssignment(
        target=".cataforge/skills/task-decomp/SKILL.md",
        adapter="task_decompose",
        config=_task_decompose_config(_schema_rel("doc-gen", "task")),
    ))
    plans.append(TargetAssignment(
        target=".cataforge/skills/doc-review/SKILL.md",
        adapter="doc_read",
        config=_doc_read_config({
            "doc_features": _PRE_FEATURES_IN_DOC,
            "doc_modules": _PRE_MODULES_IN_DOC,
        }),
    ))
    plans.append(TargetAssignment(
        target=".cataforge/skills/doc-nav/SKILL.md",
        adapter="doc_read",
        config=_doc_read_config(),
    ))

    # ---- Review / audit skills (9) ----
    review_skills = (
        "code-review", "tdd-engine", "testing",
        "platform-audit", "framework-review", "framework-feedback",
        "research", "tech-eval", "sprint-review",
    )
    for skill in review_skills:
        plans.append(TargetAssignment(
            target=f".cataforge/skills/{skill}/SKILL.md",
            adapter="doc_read",
            config=_doc_read_config(),
        ))

    return plans


# ---------- frontmatter helpers ----------

_FRONTMATTER_DELIM = "---"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str, str]:
    """Return (parsed_frontmatter, raw_frontmatter_text, body).

    The original raw text is preserved so non-affected fields round-trip
    byte-for-byte when the YAML parser would otherwise normalise quoting
    / ordering. The parsed dict drives the kg_adapter merge decision."""
    if not text.startswith(_FRONTMATTER_DELIM):
        raise AdapterMigrationError("file does not start with YAML frontmatter")
    _close_lf = f"\n{_FRONTMATTER_DELIM}\n"
    _close_crlf = f"\n{_FRONTMATTER_DELIM}\r\n"
    end_lf = text.find(_close_lf, len(_FRONTMATTER_DELIM))
    end_crlf = text.find(_close_crlf, len(_FRONTMATTER_DELIM))
    if end_lf == -1 and end_crlf == -1:
        raise AdapterMigrationError(
            "frontmatter delimiter `---` not closed"
        )
    if end_lf != -1 and (end_crlf == -1 or end_lf <= end_crlf):
        end = end_lf
        body_start = end + len(_close_lf)
    else:
        end = end_crlf
        body_start = end + len(_close_crlf)
    raw = text[len(_FRONTMATTER_DELIM):end]
    body = text[body_start:]
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise AdapterMigrationError(
            f"invalid YAML frontmatter: {exc}",
        ) from exc
    if not isinstance(data, dict):
        raise AdapterMigrationError(
            f"frontmatter must be a YAML mapping, got {type(data).__name__}",
        )
    return data, raw, body


def _render_block(block: dict[str, Any]) -> str:
    """Render a single ``kg_adapter`` block as YAML.

    ``default_flow_style=False`` keeps the block style humans expect;
    ``sort_keys=False`` preserves field order; ``width=10**9`` prevents
    the dumper from wrapping long SPARQL strings mid-string."""
    rendered: str = yaml.safe_dump(
        {"kg_adapter": block},
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=10 ** 9,
    )
    return rendered


def _locate_existing_block(raw_fm: str) -> tuple[int, int] | None:
    """Find the ``kg_adapter:`` block in raw frontmatter text.

    Returns ``(start_line_idx, end_line_idx_exclusive)`` or None. The
    block starts at the ``kg_adapter:`` line and ends at the first
    line that is not blank and not indented (the next top-level key)."""
    lines = raw_fm.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if line.startswith("kg_adapter:"):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].lstrip()
        if stripped == "":
            continue
        # Top-level key (unindented and not part of the kg_adapter block).
        if lines[j][:1] not in (" ", "\t"):
            end = j
            break
    return start, end


def _inject_kg_adapter(
    text: str, adapter_name: str, config: dict[str, Any],
) -> tuple[str, bool]:
    """Return ``(new_text, changed)`` after splicing the kg_adapter block.

    Idempotent: if the existing block parses to the same proposed value
    ``changed`` is False and ``new_text`` equals the input. Text-based
    splicing preserves the surrounding frontmatter formatting (quoting,
    indentation, comments) so the migration diff is minimal."""
    data, raw_fm, body = _split_frontmatter(text)
    proposed = {"name": adapter_name, "config": config}
    if data.get("kg_adapter") == proposed:
        return text, False

    rendered = _render_block(proposed).rstrip("\n") + "\n"

    raw_lines = raw_fm.splitlines(keepends=True)
    located = _locate_existing_block(raw_fm)
    if located is None:
        # Append at the end of the frontmatter, preserving the prior
        # content verbatim. Ensure a newline boundary first.
        prefix = raw_fm if raw_fm.endswith("\n") else raw_fm + "\n"
        new_fm = prefix + rendered
    else:
        start, end = located
        before = "".join(raw_lines[:start])
        after = "".join(raw_lines[end:])
        new_fm = before + rendered + after

    new_text = (
        f"{_FRONTMATTER_DELIM}{new_fm}{_FRONTMATTER_DELIM}\n{body}"
    )
    return new_text, True


# ---------- top-level driver ----------

def migrate_adapters(
    project_root: Path,
    *,
    plan: Iterable[TargetAssignment] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> MigrationReport:
    """Apply (or report) the adapter migration plan against a project root.

    ``dry_run`` skips all file writes — useful for CI gating. ``force``
    rewrites existing ``kg_adapter`` blocks even when they differ from
    the canonical config (default is to skip user-customised blocks).
    Schema files are always preserved when they exist; force does not
    overwrite them — the adapter migration owns the *frontmatter* contract,
    not the schemas themselves."""
    report = MigrationReport()
    plans = list(plan if plan is not None else default_plan())
    for assignment in plans:
        target_path = project_root / assignment.target
        if not target_path.is_file():
            report.targets_missing.append(target_path)
            continue

        # Validate the named adapter exists so a typo in the plan fails fast.
        get_adapter(assignment.adapter)

        original = target_path.read_text(encoding="utf-8")
        try:
            data, _, _ = _split_frontmatter(original)
        except AdapterMigrationError as exc:
            raise AdapterMigrationError(
                f"{target_path}: {exc}",
            ) from exc

        existing_block = data.get("kg_adapter")
        if existing_block is not None and not force:
            report.frontmatter_skipped.append(target_path)
        else:
            new_text, changed = _inject_kg_adapter(
                original, assignment.adapter, assignment.config,
            )
            if changed:
                if not dry_run:
                    target_path.write_text(new_text, encoding="utf-8")
                report.frontmatter_written.append(target_path)
            else:
                report.frontmatter_skipped.append(target_path)

        if assignment.schema_path and assignment.schema_body is not None:
            schema_target = project_root / assignment.schema_path
            if schema_target.is_file():
                report.schemas_skipped.append(schema_target)
            else:
                if not dry_run:
                    schema_target.parent.mkdir(parents=True, exist_ok=True)
                    schema_target.write_text(
                        json.dumps(
                            assignment.schema_body, indent=2, ensure_ascii=False,
                        ) + "\n",
                        encoding="utf-8",
                    )
                report.schemas_written.append(schema_target)

    return report
