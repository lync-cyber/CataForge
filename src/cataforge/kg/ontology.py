"""Namespace registry and ontology / SHACL shape loaders.

Three responsibilities:

1. Hold the single source of truth for built-in CURIE prefixes (cfk / cfp /
   cfa / rdf / rdfs / owl / xsd / sh / dct). :mod:`cataforge.kg.store` and
   any other consumer that needs to expand short tokens reads from
   :data:`NAMESPACES` here.

2. Load the bundled L0 / L1 / L2 ``.ttl`` files (``data/{kernel,process,
   artifact}.ttl``) plus their SHACL shapes into one Graph each. Bundled
   files are resolved via :mod:`importlib.resources` so they keep working
   both in editable installs and inside the wheel.

3. Read the optional ``kg`` block from ``<project_root>/.cataforge/
   framework.json`` to attach L3 project-domain ontologies and L3
   namespace prefixes, per design note §1.9.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from importlib.resources import as_file, files
from pathlib import Path

from rdflib import Graph
from rdflib.namespace import NamespaceManager

# Single source of truth for built-in CURIE prefixes. Adding a prefix here
# automatically makes it expandable in store.Triple and queryable as a
# short name in SPARQL via Graph.bind().
NAMESPACES: dict[str, str] = {
    "cfk":  "https://cataforge.dev/ontology/kernel#",
    "cfp":  "https://cataforge.dev/ontology/process#",
    "cfa":  "https://cataforge.dev/ontology/artifact#",
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl":  "http://www.w3.org/2002/07/owl#",
    "xsd":  "http://www.w3.org/2001/XMLSchema#",
    "sh":   "http://www.w3.org/ns/shacl#",
    "dct":  "http://purl.org/dc/terms/",
}

BUILTIN_ONTOLOGY_FILES: tuple[str, ...] = ("kernel", "process", "artifact")
BUILTIN_SHAPE_FILES: tuple[str, ...] = (
    "kernel.shacl",
    "process.shacl",
    "artifact.shacl",
)

FRAMEWORK_CONFIG_PATH = ".cataforge/framework.json"


class OntologyError(RuntimeError):
    """Raised when ontology / shape loading fails (missing file, bad TTL,
    L3 namespace conflicting with a built-in prefix)."""


def bind_namespaces(target: Graph | NamespaceManager) -> None:
    """Bind all :data:`NAMESPACES` to a Graph (or its NamespaceManager).

    Idempotent — re-binding the same prefix overrides the previous mapping
    so callers can safely call this on graphs that have other bindings."""
    nm = target if isinstance(target, NamespaceManager) else target.namespace_manager
    for prefix, iri in NAMESPACES.items():
        nm.bind(prefix, iri, override=True)


def builtin_ttl_path(stem: str) -> Path:
    """Return a filesystem path to a bundled ``data/<stem>.ttl`` resource.

    Uses ``importlib.resources.as_file`` so the call works whether the
    package is installed as a regular wheel or in editable mode pointing
    at ``src/cataforge/kg/data/``.

    Callers must use the returned path before any wheel-extraction temp
    directories are cleaned up. For long-lived use, prefer
    :func:`_read_builtin_ttl_bytes`."""
    res = files("cataforge.kg").joinpath("data").joinpath(f"{stem}.ttl")
    with as_file(res) as fp:
        path = Path(fp)
    if not path.is_file():
        raise OntologyError(f"Bundled ontology file not found: {res}")
    return path


def _read_builtin_ttl(stem: str) -> bytes:
    """Return the raw bytes of a bundled ``data/<stem>.ttl`` resource.

    Safe to call in both editable and wheel installs — no filesystem path
    escapes the call."""
    res = files("cataforge.kg").joinpath("data").joinpath(f"{stem}.ttl")
    try:
        return res.read_bytes()
    except (FileNotFoundError, TypeError) as exc:
        raise OntologyError(f"Bundled ontology file not found: {res}") from exc


def load_framework_kg_config(project_root: str | Path) -> dict[str, object]:
    """Read the ``kg`` block from ``<project_root>/.cataforge/framework.json``.

    Returns an empty dict when the config file or the ``kg`` block is
    absent — L3 customisation is optional."""
    root = Path(project_root).resolve()
    cfg_path = root / FRAMEWORK_CONFIG_PATH
    if not cfg_path.is_file():
        return {}
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OntologyError(
            f"Failed to parse {cfg_path}: {exc.msg} at line {exc.lineno}",
        ) from exc
    kg = raw.get("kg", {})
    if not isinstance(kg, dict):
        raise OntologyError(
            f"{cfg_path}: 'kg' block must be an object, got {type(kg).__name__}",
        )
    return kg


def _resolve_l3_files(
    project_root: Path,
    files_in_config: object,
) -> list[Path]:
    """Coerce a config-supplied list of ontology file paths to absolute Paths.

    Relative paths resolve against ``project_root``. Missing files raise
    OntologyError so users notice typos rather than getting silent skips."""
    if files_in_config is None:
        return []
    if not isinstance(files_in_config, list):
        raise OntologyError(
            f"kg.ontology_files must be a list, got {type(files_in_config).__name__}",
        )
    resolved: list[Path] = []
    for entry in files_in_config:
        if not isinstance(entry, str):
            raise OntologyError(
                f"kg.ontology_files entries must be strings, got {entry!r}",
            )
        p = Path(entry)
        if not p.is_absolute():
            p = (project_root / p).resolve()
        if not p.is_file():
            raise OntologyError(f"L3 ontology file not found: {p}")
        resolved.append(p)
    return resolved


def _bind_l3_namespaces(
    target: Graph,
    namespaces_in_config: object,
) -> None:
    """Register L3 prefixes on the graph, refusing to shadow built-ins."""
    if namespaces_in_config is None:
        return
    if not isinstance(namespaces_in_config, dict):
        raise OntologyError(
            f"kg.namespaces must be an object, got "
            f"{type(namespaces_in_config).__name__}",
        )
    for prefix, iri in namespaces_in_config.items():
        if prefix in NAMESPACES:
            raise OntologyError(
                f"L3 prefix {prefix!r} conflicts with built-in; choose a "
                "project-specific prefix.",
            )
        if not isinstance(iri, str):
            raise OntologyError(
                f"L3 namespace IRI for {prefix!r} must be a string.",
            )
        target.namespace_manager.bind(prefix, iri, override=True)


def load_ontology(
    project_root: str | Path,
    *,
    include_l3: bool = True,
    strict: bool = True,
) -> Graph:
    """Load all built-in L0/L1/L2 ontologies plus optional L3 into one Graph.

    ``strict=False`` lets the caller tolerate missing bundled files (used
    during bootstrapping when ``data/*.ttl`` are themselves being authored);
    in production callers should always leave it True so a misshipped
    wheel fails loudly."""
    root = Path(project_root).resolve()
    graph = Graph()
    bind_namespaces(graph)

    _parse_builtin(graph, BUILTIN_ONTOLOGY_FILES, strict=strict)

    if include_l3:
        cfg = load_framework_kg_config(root)
        _bind_l3_namespaces(graph, cfg.get("namespaces"))
        for path in _resolve_l3_files(root, cfg.get("ontology_files")):
            graph.parse(source=str(path))

    return graph


def load_shapes(
    project_root: str | Path,
    *,
    include_l3: bool = True,
    strict: bool = True,
) -> Graph:
    """Load all built-in SHACL shapes plus optional L3 shape files.

    L3 shape paths live under ``kg.shape_files`` in framework.json (a
    separate list from ``kg.ontology_files`` so projects can ship pure
    constraint refinements without re-declaring class taxonomy)."""
    root = Path(project_root).resolve()
    graph = Graph()
    bind_namespaces(graph)

    _parse_builtin(graph, BUILTIN_SHAPE_FILES, strict=strict)

    if include_l3:
        cfg = load_framework_kg_config(root)
        _bind_l3_namespaces(graph, cfg.get("namespaces"))
        for path in _resolve_l3_files(root, cfg.get("shape_files")):
            graph.parse(source=str(path))

    return graph


def _parse_builtin(graph: Graph, stems: Iterable[str], *, strict: bool) -> None:
    for stem in stems:
        res = files("cataforge.kg").joinpath("data").joinpath(f"{stem}.ttl")
        try:
            with as_file(res) as fp:
                if not Path(fp).is_file():
                    raise OntologyError(f"Bundled ontology file not found: {res}")
                graph.parse(source=str(fp), format="turtle")
        except OntologyError:
            if strict:
                raise
            continue
