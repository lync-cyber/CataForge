"""Jinja2 environment + render driver for KG → Markdown.

The renderer assumes templates live under one or more "template roots"
(by convention ``.cataforge/skills/doc-gen/templates/`` and project-local
``docs/templates/``) and ship with the ``.md.j2`` extension. It exposes
three Jinja globals:

* ``kg``         — a wrapper exposing :meth:`query`, :meth:`get_attr`,
                   :meth:`subgraph`, all keyed off the bound store.
* ``sparql``     — a free-standing wrapper around ``kg.query`` for
                   templates that prefer a function-call style.
* ``namespaces`` — the bundled CURIE → IRI map (read-only).

There is deliberately **no** ``now()`` global: timestamps inside rendered
output would break the render-twice idempotency invariant (design §4.3 /
risk R-03). Templates that want a "generated_by" provenance line use the
:data:`GENERATED_BY_MARKER` constant which never changes between runs."""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

from cataforge.kg.ontology import NAMESPACES
from cataforge.kg.query import _expand_curie
from cataforge.kg.render.filters import (
    bullet_list,
    link_to,
    mermaid_diagram,
    table,
)
from cataforge.kg.store import GraphStore

GENERATED_BY_MARKER = "cataforge-kg-render"


class RenderError(RuntimeError):
    """Raised on template lookup or render-time failures."""


class _KGGlobal:
    """The ``kg`` global injected into every template."""

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def query(self, sparql: str, **params: Any) -> list[dict[str, str]]:
        """Run a SPARQL SELECT/ASK with optional ``$name`` substitutions.

        Uses :class:`string.Template` syntax (``$name`` or ``${name}``)
        rather than ``str.format`` so SPARQL's literal ``{`` / ``}`` in
        WHERE clauses don't need escaping. Each value is IRI-passed if it
        parses as a CURIE / absolute IRI, otherwise quoted as a SPARQL
        string literal — defends against the common injection vector
        (a SPARQL value containing a ``>`` character).
        """
        if params or "$" in sparql:
            safe_params = {k: _safe_format_value(v) for k, v in params.items()}
            tpl = Template(sparql)
            missing = {
                m.group("named") or m.group("braced")
                for m in tpl.pattern.finditer(sparql)
                if (m.group("named") or m.group("braced")) and
                   (m.group("named") or m.group("braced")) not in safe_params
            }
            if missing:
                raise RenderError(
                    f"missing template parameter(s) {sorted(missing)!r} for kg.query",
                )
            sparql = tpl.safe_substitute(**safe_params)
        prefix_header = "\n".join(f"PREFIX {p}: <{iri}>" for p, iri in NAMESPACES.items())
        return self._store.query(prefix_header + "\n" + sparql)

    def get_attr(
        self,
        subject_iri: str,
        predicate: str,
        *,
        default: str = "",
    ) -> str:
        """Return the first ``?o`` for (subject, predicate) or *default*."""
        try:
            full_subj = _expand_curie(subject_iri)
        except ValueError:
            return default
        rows = self.query(
            f"SELECT ?o WHERE {{ <{full_subj}> {predicate} ?o }} LIMIT 1",
        )
        return rows[0]["o"] if rows else default

    def subgraph(
        self,
        root: str,
        *,
        depth: int = 2,
    ) -> list[dict[str, str]]:
        """Return triples reachable from *root* within *depth* hops.

        Output rows are ``{src, dst, predicate}`` ready to hand to the
        ``mermaid_diagram`` filter. ``depth`` is materialised via SPARQL
        property paths of the form ``(?p1|?p2)?{n}``; cycles are broken
        by the SPARQL engine's bag semantics, so the worst case is bounded
        by the cartesian product of unique predicates."""
        full_root = _expand_curie(root)
        rows = self.query(
            "SELECT DISTINCT ?src ?predicate ?dst WHERE {\n"
            f"  <{full_root}> (<>|!<>){{0,{depth}}} ?src .\n"
            "  ?src ?predicate ?dst .\n"
            "  FILTER (isIRI(?dst))\n"
            "} ORDER BY ?src ?predicate ?dst",
        )
        return rows


def _safe_format_value(value: Any) -> str:
    """Render a Python value for safe SPARQL string-format substitution.

    CURIEs and absolute IRIs are expanded and angle-bracketed so SPARQL's
    prefixed-name parser doesn't reject local parts that contain ``/``
    (which our IRI scheme ``cfa:<doc-slug>/<display-id>`` always does)."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        if value.startswith(("http://", "https://", "urn:")):
            return f"<{value}>"
        if ":" in value and value.split(":", 1)[0] in NAMESPACES:
            return f"<{_expand_curie(value)}>"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class KGRenderer:
    """Jinja2 renderer bound to a :class:`GraphStore`.

    Construct once per render session (caches the template environment);
    call :meth:`render` per template. Template roots are searched in
    order, so project-local templates can shadow bundled ones."""

    def __init__(
        self,
        store: GraphStore,
        template_roots: list[Path] | None = None,
    ) -> None:
        self._store = store
        self._roots = list(template_roots or [])
        self._env = self._build_env()
        kg_global = _KGGlobal(store)
        self._env.globals["kg"] = kg_global
        self._env.globals["sparql"] = kg_global.query
        self._env.globals["namespaces"] = dict(NAMESPACES)
        self._env.globals["generated_by"] = GENERATED_BY_MARKER
        self._env.filters["bullet_list"] = bullet_list
        self._env.filters["table"] = table
        self._env.filters["mermaid_diagram"] = mermaid_diagram
        self._env.filters["link_to"] = link_to

    def _build_env(self) -> Environment:
        if not self._roots:
            return Environment(
                autoescape=select_autoescape(default=False),
                trim_blocks=True,
                lstrip_blocks=True,
                keep_trailing_newline=True,
                undefined=StrictUndefined,
            )
        loaders = [FileSystemLoader(str(r)) for r in self._roots]
        return Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(default=False),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            undefined=StrictUndefined,
        )

    def render(self, template_name: str, **context: Any) -> str:
        """Render a template (resolved relative to any template root)."""
        try:
            template = self._env.get_template(template_name)
        except Exception as exc:
            raise RenderError(
                f"failed to load template {template_name!r}: {exc}",
            ) from exc
        try:
            return template.render(**context)
        except Exception as exc:
            raise RenderError(
                f"failed to render {template_name!r}: {exc}",
            ) from exc

    def render_string(self, source: str, **context: Any) -> str:
        """Render a template provided as a literal string — for tests and
        the ``kg render --inline`` future CLI flag."""
        try:
            return self._env.from_string(source).render(**context)
        except Exception as exc:
            raise RenderError(f"inline render failed: {exc}") from exc
