"""SPARQL template registry — one `.sparql` file per entity type.

The lookup key is the lowercased LinkML class name; the file stem in
`sparql/` must match. Sub-PR 4 ships built-ins for the four entity
types in the fixture vertical slice (Feature / AcceptanceCriteria /
Module / TestCase); other types land alongside the call points that
need them in later sub-PRs.
"""
from __future__ import annotations

from pathlib import Path

_BUILTIN_SPARQL_DIR = Path(__file__).parent / "sparql"


class SparqlRegistry:
    """Maps entity-type (lower-case class name) → SPARQL template string."""

    def __init__(self, builtin_dir: Path = _BUILTIN_SPARQL_DIR) -> None:
        self._templates: dict[str, str] = {}
        for path in sorted(builtin_dir.glob("*.sparql")):
            self._templates[path.stem.lower()] = path.read_text(encoding="utf-8")

    def get(self, entity_type: str) -> str:
        key = entity_type.lower()
        try:
            return self._templates[key]
        except KeyError as exc:
            raise KeyError(
                f"No SPARQL template registered for entity type '{entity_type}'. "
                f"Add `{key}.sparql` under cataforge/kg/export/sparql/."
            ) from exc

    def registered_types(self) -> list[str]:
        return sorted(self._templates)

    def has(self, entity_type: str) -> bool:
        return entity_type.lower() in self._templates
