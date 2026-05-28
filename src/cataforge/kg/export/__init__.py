"""KG → Markdown export pipeline.

Entry points: `compile_to_markdown(store, output_dir)` for full-store
export, and `render_entity(store, entity_id, *, template=None)` for
single-entity rendering used by the shim layer. The Jinja2 + SPARQL
template trees ship as package data under `templates/` and `sparql/`.
"""

from __future__ import annotations

from cataforge.kg.export.pipeline import compile_to_markdown
from cataforge.kg.export.registry import SparqlRegistry
from cataforge.kg.export.render import entity_doc_type, render_entity
from cataforge.kg.export.types import CompileResult, FileExportRecord

__all__ = [
    "CompileResult",
    "FileExportRecord",
    "SparqlRegistry",
    "compile_to_markdown",
    "entity_doc_type",
    "render_entity",
]
