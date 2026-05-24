"""CataForge knowledge graph layer.

Subpackage layout follows the five-layer architecture from
``docs/research/kg-feature-upgrade-design.md`` §5:

- ``store``       — :class:`GraphStore` ABC + ``RDFLibStore`` default backend
- ``ontology``    — namespace registry + ``.ttl`` / SHACL shape loader
- ``ingest``      — markdown → triples (frontmatter, prose refs, canonical)
- ``render``      — Jinja2 + SPARQL → markdown
- ``query``       — SPARQL / Cypher-lite / DSL unified entry
- ``reasoning``   — OWL-RL (restricted profile) + pyshacl validation
- ``delta``       — three-way merge between KG, file, render
- ``adapters``    — :class:`KGAdapter` registry + builtin adapters
- ``benchmark``   — perf-budget gate harness
- ``migrate``     — one-shot ``.doc-index.json`` → KG migration
"""

from __future__ import annotations

__all__: list[str] = []
