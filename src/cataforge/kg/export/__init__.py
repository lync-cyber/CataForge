"""KG → Markdown export pipeline (task-4).

Sub-PR 4 surface: a single `compile_to_markdown(store, output_dir)`
entry point plus dataclasses describing the result. The Jinja2 +
SPARQL template trees ship as package data under `templates/` and
`sparql/`.

Sub-PR 5 errata C2: `render_entity(store, entity_id, *, template=None)`
exposes a single-entity render path used by the shim layer.
"""
from __future__ import annotations

from cataforge.kg.export.pipeline import compile_to_markdown
from cataforge.kg.export.registry import SparqlRegistry
from cataforge.kg.export.render import entity_doc_type, render_entity
from cataforge.kg.export.template_loader import build_jinja_env
from cataforge.kg.export.types import CompileResult, FileExportRecord

__all__ = [
    "CompileResult",
    "FileExportRecord",
    "SparqlRegistry",
    "build_jinja_env",
    "compile_to_markdown",
    "entity_doc_type",
    "render_entity",
]
