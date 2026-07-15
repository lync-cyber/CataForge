"""Walk LinkML `is_a` chain → `rdfs:subClassOf` axioms.

`scripts/codegen_kg_schema.py` runs the walk (`iter_subclass_axioms` /
`prefix_map`) to write `_generated/subclass_axioms.ttl`; those functions
need the linkml stack from the `dev` extra. The runtime side
(`cataforge.domain.kg._store.bootstrap_subclass_axioms()`) only reads the
packaged artifact via `packaged_axioms_path()` — the published wheel has no
linkml dependency.

pyoxigraph 0.5.x performs no OWL/RDFS entailment, so property-path queries
like `a/rdfs:subClassOf*` only traverse triples that are explicitly present.
Materializing the `is_a` chain at bootstrap closes this gap.
"""

from __future__ import annotations

import importlib.resources
from collections.abc import Iterator
from pathlib import Path

CORE_SCHEMA = "core.yaml"
GOVERNANCE_SCHEMA = "governance.yaml"

# Mirrors the `cfgov:` prefix in schemas/governance.yaml; equivalence is
# pinned by tests/kg/test_store.py::test_bootstrap_axioms_match_schema_walk.
GOVERNANCE_NS = "https://cataforge.dev/governance/"


def packaged_axioms_path() -> Path:
    """Absolute path to the packaged `subclass_axioms.ttl` artifact.

    Resolves via `importlib.resources` so editable installs and wheels agree;
    the artifact is committed and shipped inside the wheel (freshness against
    the schemas is enforced by `scripts/checks/check_codegen_fresh.py`).
    """
    base = importlib.resources.files("cataforge.domain.kg")
    return Path(str(base / "_generated" / "subclass_axioms.ttl"))


def schema_paths(include_governance: bool = False) -> list[Path]:
    """Return absolute paths to the packaged schema files.

    Resolves via `importlib.resources` so editable installs, wheels, and
    direct `python -m` invocations all agree on the same files.
    """
    base = importlib.resources.files("cataforge.domain.kg.schemas")
    paths = [Path(str(base / CORE_SCHEMA))]
    if include_governance:
        paths.append(Path(str(base / GOVERNANCE_SCHEMA)))
    return paths


def iter_subclass_axioms(
    yaml_paths: list[Path] | None = None,
    *,
    include_governance: bool = False,
) -> Iterator[tuple[str, str]]:
    """Yield `(child_uri, parent_uri)` pairs in deterministic sorted order.

    Both URIs are returned in CURIE form (e.g. `cf:Feature`) when the
    schema declares a prefix for them; otherwise an HTTP IRI is returned
    unchanged. Callers that need full IRIs should expand prefixes via
    the prefix map returned by `prefix_map()`.
    """
    from linkml_runtime.utils.schemaview import SchemaView

    if yaml_paths is None:
        yaml_paths = schema_paths(include_governance=include_governance)

    pairs: set[tuple[str, str]] = set()
    for yaml_path in yaml_paths:
        sv = SchemaView(str(yaml_path))
        for cls_name in sv.all_classes():
            cls = sv.get_class(cls_name)
            if not cls.is_a:
                continue
            parent = sv.get_class(cls.is_a)
            if parent is None:
                continue
            child_uri = sv.get_uri(cls, expand=False) or f"cf:{cls.name}"
            parent_uri = sv.get_uri(parent, expand=False) or f"cf:{parent.name}"
            pairs.add((child_uri, parent_uri))

    yield from sorted(pairs)


def prefix_map(
    yaml_paths: list[Path] | None = None,
    *,
    include_governance: bool = False,
) -> dict[str, str]:
    """Return the merged prefix → URI map declared across the schema files.

    Always includes `rdfs` even if no schema declares it, so callers
    rendering Turtle / inserting triples have the canonical namespace.
    """
    from linkml_runtime.utils.schemaview import SchemaView

    if yaml_paths is None:
        yaml_paths = schema_paths(include_governance=include_governance)

    namespaces: dict[str, str] = {}
    for yaml_path in yaml_paths:
        sv = SchemaView(str(yaml_path))
        for prefix_name, prefix_obj in sv.schema.prefixes.items():
            namespaces.setdefault(prefix_name, prefix_obj.prefix_reference)

    namespaces.setdefault("rdfs", "http://www.w3.org/2000/01/rdf-schema#")
    return namespaces


def expand_curie(curie: str, prefixes: dict[str, str]) -> str:
    """Expand `prefix:local` to a full IRI using `prefixes`. Pass IRIs through."""
    if ":" not in curie:
        return curie
    head, tail = curie.split(":", 1)
    if tail.startswith("//"):
        return curie
    base = prefixes.get(head)
    if base is None:
        return curie
    return f"{base}{tail}"
