"""SPARQL template registry — one `.sparql` file per entity type.

The lookup key is the lowercased LinkML class name; the file stem in
`sparql/` must match. Bespoke templates cover the richer entity types
(Feature, Module, TestCase, …) with their relations. Any other
SoftwareArtifact subclass resolves to the generic `_artifact.sparql`,
which fetches the core slots — so every class renders without a per-class
file. Add a bespoke `{class}.sparql` to surface that class's relations.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.domain.kg.export._entity_meta import GENERIC_SPARQL_KEY

_BUILTIN_SPARQL_DIR = Path(__file__).parent / "sparql"


class SparqlRegistry:
    """Maps entity-type (lower-case class name) → SPARQL template string."""

    def __init__(self, builtin_dir: Path = _BUILTIN_SPARQL_DIR) -> None:
        self._templates: dict[str, str] = {}
        for path in sorted(builtin_dir.glob("*.sparql")):
            self._templates[path.stem.lower()] = path.read_text()
        if GENERIC_SPARQL_KEY not in self._templates:
            raise KeyError(
                f"Generic SPARQL template '{GENERIC_SPARQL_KEY}.sparql' is missing "
                f"under {builtin_dir}; it is the render fallback for every class."
            )

    def get(self, entity_type: str) -> str:
        """Return the bespoke template for `entity_type`, else the generic one."""
        return self._templates.get(entity_type.lower(), self._templates[GENERIC_SPARQL_KEY])

    def registered_types(self) -> list[str]:
        return sorted(self._templates)
