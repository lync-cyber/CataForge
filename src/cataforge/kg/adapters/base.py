"""KGAdapter ABC plus the schema-driven default implementation.

The base class enforces the design §3.2 contract: every adapter exposes
``pre_dispatch_context`` (KG → prompt) and ``write_back`` (LLM output →
KG). :class:`SchemaDrivenAdapter` provides both by consuming two config
blocks (``pre_dispatch_queries`` and ``write_back_schema``) so the five
authoring built-ins reduce to a name + config-schema declaration.

The :func:`triples_from_schema` helper is the canonical agent-output →
triples converter. The schema format is a JSON document describing how
to materialise each item in the agent's output dict into a typed entity
with literals + IRI references. It deliberately stays narrower than
generic JSON Schema — the only contract is "convert a known shape into
triples" — but the file extension ``.schema.json`` is retained so editor
schema-validation tooling still recognises it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, ClassVar

from cataforge.kg.ontology import NAMESPACES
from cataforge.kg.store import GraphStore, Triple, ValidationReport


class AdapterError(RuntimeError):
    """Raised on adapter config / schema / dispatch failures."""


@dataclass(frozen=True)
class AdapterDispatchResult:
    """Outcome of a :meth:`KGAdapter.write_back` followed by validation."""

    triples: list[Triple]
    report: ValidationReport | None


class KGAdapter(ABC):
    """Contract between a SKILL / AGENT dispatch and the KG.

    Subclasses set ``name`` (registry key) and ``config_schema`` (JSON
    Schema validating the ``kg_adapter.config`` block in SKILL frontmatter
    or ``framework.json``). Instances are short-lived — one per dispatch —
    and carry the ``invocation_id`` so write-back can scope its triples
    to a named graph ``cfk:invocation/<invocation_id>``."""

    name: ClassVar[str] = ""
    config_schema: ClassVar[dict[str, Any]] = {}

    def __init__(
        self,
        store: GraphStore,
        invocation_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.invocation_id = invocation_id
        self.config: dict[str, Any] = dict(config or {})

    # ---- contract ----

    @abstractmethod
    def pre_dispatch_context(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return a dict the harness serialises into the LLM prompt."""

    @abstractmethod
    def write_back(self, agent_output: dict[str, Any]) -> list[Triple]:
        """Convert agent output into triples appended to the store."""

    # ---- shared helpers ----

    def invocation_graph_iri(self) -> str:
        """Named-graph IRI used to tag this dispatch's write-back triples."""
        return f"cfk:invocation/{self.invocation_id}"

    def validate_output(
        self, triples: Iterable[Triple],
    ) -> ValidationReport | None:
        """Optionally re-run SHACL after write-back; default re-validates the
        full store. Adapters that need shape-scoped validation should
        override; returning ``None`` skips entirely."""
        del triples  # validation is store-wide today; param reserved
        try:
            return self.store.validate()
        except Exception as exc:  # pragma: no cover — best-effort hook
            raise AdapterError(f"post-write-back validate failed: {exc}") from exc

    def run_query(
        self, sparql: str, params: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        """Run a SPARQL query with ``$name`` parameter substitution.

        Shared helper so every adapter (read-only or schema-driven) goes
        through the same safe-quoting path — CURIE / IRI values are
        angle-bracketed, scalars become typed literals, strings are
        quoted with escapes."""
        return _run_query(self.store, sparql, params or {})


class SchemaDrivenAdapter(KGAdapter):
    """Adapter that derives both halves of the contract from JSON config.

    ``config["pre_dispatch_queries"]`` is a ``{key: sparql}`` map; queries
    accept ``$name`` parameters supplied via ``params``. Results land in
    the returned dict under the same key.

    ``config["write_back_schema"]`` is a path (relative to the project
    root) to a JSON file consumed by :func:`triples_from_schema`."""

    def pre_dispatch_context(self, params: dict[str, Any]) -> dict[str, Any]:
        queries = self.config.get("pre_dispatch_queries") or {}
        if not isinstance(queries, Mapping):
            raise AdapterError(
                "config.pre_dispatch_queries must be a mapping of key → sparql"
            )
        results: dict[str, Any] = {}
        for key, sparql in queries.items():
            if not isinstance(sparql, str):
                raise AdapterError(
                    f"pre_dispatch_queries.{key} must be a SPARQL string"
                )
            results[key] = self.run_query(sparql, params)
        return results

    def write_back(self, agent_output: dict[str, Any]) -> list[Triple]:
        schema_path = self.config.get("write_back_schema")
        if not schema_path:
            raise AdapterError(
                f"adapter {self.name!r}: config.write_back_schema is required",
            )
        project_root = self.config.get("_project_root")
        schema = _load_schema(Path(schema_path), project_root)
        triples = triples_from_schema(
            agent_output,
            schema,
            context=dict(agent_output),
        )
        if triples:
            self.store.add(triples, named_graph=self.invocation_graph_iri())
        return triples


# ---------- SPARQL parameter substitution ----------

def _safe_value(value: Any) -> str:
    """Render a Python value for SPARQL ``$name`` substitution.

    CURIEs and absolute IRIs are angle-bracketed; everything else becomes
    a quoted SPARQL string literal. Mirrors
    :func:`cataforge.kg.render.engine._safe_format_value` so adapter
    SPARQL behaves the same as render-template SPARQL."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        if value.startswith(("http://", "https://", "urn:")):
            return f"<{value}>"
        if ":" in value and value.split(":", 1)[0] in NAMESPACES:
            from cataforge.kg.query import _expand_curie

            return f"<{_expand_curie(value)}>"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _run_query(
    store: GraphStore,
    sparql: str,
    params: dict[str, Any],
) -> list[dict[str, str]]:
    """Substitute ``$name`` params then prepend the standard PREFIX header."""
    if params or "$" in sparql:
        substituted = Template(sparql).safe_substitute(
            **{k: _safe_value(v) for k, v in params.items()},
        )
    else:
        substituted = sparql
    prefix_header = "\n".join(
        f"PREFIX {p}: <{iri}>" for p, iri in NAMESPACES.items()
    )
    return store.query(prefix_header + "\n" + substituted)


# ---------- write-back schema → triples ----------

def _load_schema(
    schema_path: Path, project_root: str | Path | None,
) -> dict[str, Any]:
    """Resolve a possibly-relative schema path and parse JSON."""
    import json as _json

    full = schema_path
    if not full.is_absolute() and project_root is not None:
        full = Path(project_root) / schema_path
    if not full.is_file():
        raise AdapterError(f"write-back schema not found: {full}")
    try:
        parsed = _json.loads(full.read_text(encoding="utf-8"))
    except _json.JSONDecodeError as exc:
        raise AdapterError(
            f"write-back schema {full} is not valid JSON: {exc}",
        ) from exc
    if not isinstance(parsed, dict):
        raise AdapterError(
            f"write-back schema {full} must be a JSON object, got {type(parsed).__name__}",
        )
    return parsed


def triples_from_schema(
    output: dict[str, Any],
    schema: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> list[Triple]:
    """Convert an agent-output dict into triples per a write-back schema.

    Schema shape (one root key, ``items``)::

        {
          "items": [
            {
              "from": "<key in agent output, list of dicts>",
              "iri": "cfa:${doc_id}/${id}",
              "type": "cfa:Feature",
              "literals": {
                "rdfs:label": "label",
                "cfa:status": {"field": "status", "optional": true}
              },
              "iri_refs": {
                "cfk:definedIn": "${doc_iri}",
                "cfa:implements": {"field": "implements", "as_iri": true}
              }
            }
          ]
        }

    ``literals`` may name fields as raw strings (required) or dicts with
    ``field`` + ``optional``. ``iri_refs`` values may be either a string
    template resolved against item + context, or a dict pointing at a
    field whose value is itself a CURIE / IRI.

    The function never mutates the store — return the list and let the
    caller add() it under an appropriate named graph."""
    # Default context to the output dict itself so top-level scalars
    # (doc_id, doc_iri, ...) flow into ${name} templates without callers
    # having to thread them through twice.
    ctx = dict(context if context is not None else output)
    items_decls = schema.get("items", [])
    if not isinstance(items_decls, list):
        raise AdapterError("schema.items must be a list")
    triples: list[Triple] = []
    for decl in items_decls:
        triples.extend(_materialise_item_decl(decl, output, ctx))
    return triples


def _materialise_item_decl(
    decl: dict[str, Any], output: dict[str, Any], ctx: dict[str, Any],
) -> list[Triple]:
    src_key = decl.get("from")
    iri_tpl = decl.get("iri")
    type_curie = decl.get("type")
    if not src_key or not iri_tpl or not type_curie:
        raise AdapterError(
            f"item decl missing required keys (from/iri/type): {decl!r}",
        )
    rows = output.get(src_key, []) or []
    if not isinstance(rows, list):
        raise AdapterError(
            f"agent output {src_key!r} must be a list, got {type(rows).__name__}"
        )
    literals_decl: dict[str, Any] = decl.get("literals", {}) or {}
    iri_refs_decl: dict[str, Any] = decl.get("iri_refs", {}) or {}

    out: list[Triple] = []
    for raw_item in rows:
        if not isinstance(raw_item, dict):
            raise AdapterError(
                f"each {src_key!r} element must be a dict, got {type(raw_item).__name__}",
            )
        item: dict[str, Any] = {**ctx, **raw_item}
        try:
            iri = Template(iri_tpl).substitute(**{
                k: v for k, v in item.items() if isinstance(v, str | int | float)
            })
        except KeyError as exc:
            raise AdapterError(
                f"item missing template field {exc.args[0]!r} for iri {iri_tpl!r}",
            ) from exc

        out.append(Triple(s=iri, p="rdf:type", o=type_curie))

        for predicate, lit_decl in literals_decl.items():
            field_name, optional = _split_field_decl(lit_decl)
            if field_name not in raw_item:
                if optional:
                    continue
                raise AdapterError(
                    f"item {iri} missing required literal field {field_name!r} "
                    f"for predicate {predicate}",
                )
            value = raw_item[field_name]
            if value is None:
                if optional:
                    continue
                raise AdapterError(
                    f"item {iri} field {field_name!r} is null but required",
                )
            out.append(Triple(s=iri, p=predicate, o=value))

        for predicate, ref_decl in iri_refs_decl.items():
            object_iri = _resolve_iri_ref(ref_decl, raw_item, item)
            if object_iri is None:
                continue
            if isinstance(object_iri, list):
                for o in object_iri:
                    out.append(Triple(s=iri, p=predicate, o=o))
            else:
                out.append(Triple(s=iri, p=predicate, o=object_iri))
    return out


def _split_field_decl(decl: Any) -> tuple[str, bool]:
    """Normalise a literal field decl into ``(field_name, optional)``."""
    if isinstance(decl, str):
        return decl, False
    if isinstance(decl, dict):
        field = decl.get("field")
        if not isinstance(field, str):
            raise AdapterError(
                f"literal decl {decl!r} missing string `field`",
            )
        return field, bool(decl.get("optional", False))
    raise AdapterError(
        f"literal decl must be a string or dict, got {type(decl).__name__}",
    )


def _resolve_iri_ref(
    decl: Any, raw_item: dict[str, Any], merged_item: dict[str, Any],
) -> str | list[str] | None:
    """Resolve an IRI-reference declaration to an IRI string / list / None.

    String decls go through :class:`string.Template` against the merged
    item+context dict. Dict decls pull a value from ``raw_item`` and may
    be a list — in which case each element becomes a separate triple."""
    if isinstance(decl, str):
        try:
            return Template(decl).substitute(**{
                k: v for k, v in merged_item.items() if isinstance(v, str | int | float)
            })
        except KeyError as exc:
            raise AdapterError(
                f"iri_ref template missing field {exc.args[0]!r}: {decl!r}",
            ) from exc
    if isinstance(decl, dict):
        field = decl.get("field")
        if not isinstance(field, str):
            raise AdapterError(f"iri_ref dict decl missing string `field`: {decl!r}")
        optional = bool(decl.get("optional", False))
        if field not in raw_item or raw_item[field] is None:
            if optional:
                return None
            raise AdapterError(
                f"iri_ref field {field!r} missing and not optional",
            )
        value = raw_item[field]
        if isinstance(value, list):
            return [str(v) for v in value]
        return str(value)
    raise AdapterError(
        f"iri_ref decl must be a string or dict, got {type(decl).__name__}",
    )
