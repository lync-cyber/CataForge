#!/usr/bin/env python3
"""Generate Pydantic models, SHACL shapes, and rdfs:subClassOf axioms from LinkML schemas.

Reads:
  - src/cataforge/domain/kg/schemas/core.yaml
  - src/cataforge/domain/kg/schemas/governance.yaml

Writes (under src/cataforge/domain/kg/_generated/):
  - core_pydantic.py            Pydantic v2 models for the business ontology
                                (committed; imported by the runtime)
  - core_shapes.ttl             SHACL shapes for business ontology (gitignored:
                                ShaclGenerator output is order-nondeterministic,
                                see scripts/checks/check_codegen_fresh.py)
  - subclass_axioms.ttl         is_a chain materialized as rdfs:subClassOf triples
                                (committed and shipped in the wheel; `cataforge kg
                                init` loads it at store bootstrap — pyoxigraph
                                0.5.x has no RDFS entailment)

Encoding: forces PYTHONIOENCODING=utf-8 in os.environ so any linkml internals
that shell out do not hit the Windows GBK UnicodeEncodeError from spike-1 §1.4.
This script itself writes via Path.write_text(..., encoding="utf-8",
newline="\n") so generated artifacts are LF on every OS and never relies on
stdout encoding.

Idempotency: subclass_axioms.ttl is byte-identical across runs (sorted triples,
no timestamps). The Pydantic / SHACL outputs are deterministic-modulo-LinkML;
a `# Generation date:` header line is stripped and LinkML's absolute
`source_file:` metadata is rewritten to a repo-relative POSIX path, so artifacts
are byte-identical across machines / OSes (the check-in freshness guard compares
them verbatim).

Usage:
    python scripts/codegen_kg_schema.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from cataforge.utils.encoding import ensure_utf8  # noqa: E402

ensure_utf8()

SCHEMA_DIR = REPO_ROOT / "src" / "cataforge" / "domain" / "kg" / "schemas"

DEFAULT_OUT_DIR = REPO_ROOT / "src" / "cataforge" / "domain" / "kg" / "_generated"

CORE_YAML = SCHEMA_DIR / "core.yaml"
GOVERNANCE_YAML = SCHEMA_DIR / "governance.yaml"


_SOURCE_FILE_RE = re.compile(r"('source_file':\s*')([^']*)(')")


def _strip_timestamps(text: str) -> str:
    keep = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("# Generation date:"):
            continue
        keep.append(line)
    return "".join(keep)


def _normalize(text: str, yaml_path: Path) -> str:
    """Strip the generation-date line and rewrite LinkML's machine-specific
    absolute `source_file:` path to a repo-relative POSIX path."""
    rel = yaml_path.resolve().relative_to(REPO_ROOT).as_posix()
    text = _SOURCE_FILE_RE.sub(lambda m: f"{m.group(1)}{rel}{m.group(3)}", text)
    return _strip_timestamps(text)


def gen_pydantic(yaml_path: Path, out_path: Path) -> None:
    from linkml.generators.pydanticgen import PydanticGenerator

    gen = PydanticGenerator(str(yaml_path))
    out_path.write_text(_normalize(gen.serialize(), yaml_path), encoding="utf-8", newline="\n")


def _blank_node_labels(graph: Any) -> dict[Any, Any] | None:
    """Deterministic blank-node labels when the graph's blank nodes form a
    forest, else ``None``.

    ShaclGenerator emits every blank node as the object of exactly one triple
    (property shapes nested under a node shape, RDF-list cells), so the blank
    nodes form a forest rooted at named subjects. For a forest, a stable label
    is a pure function of a node's rooted path plus its recursive content — no
    graph-isomorphism search needed. Returns ``None`` when that shape does not
    hold (a blank node with zero or multiple incoming edges), so the caller
    can fall back to the general canonicalizer.
    """
    from collections import defaultdict

    import rdflib

    bnodes = [n for n in graph.all_nodes() if isinstance(n, rdflib.BNode)]
    parents: dict[Any, Any] = {}
    for subject, predicate, obj in graph:
        if isinstance(obj, rdflib.BNode):
            if obj in parents:
                return None  # multiple incoming edges — not a forest
            parents[obj] = (subject, predicate)
    if any(b not in parents for b in bnodes):
        return None  # a blank node with no incoming edge — not rooted

    content_cache: dict[Any, str] = {}

    def content_sig(node: Any) -> str:
        cached = content_cache.get(node)
        if cached is not None:
            return cached
        parts = [
            f"{predicate.n3()} {content_sig(obj) if isinstance(obj, rdflib.BNode) else obj.n3()}"
            for predicate, obj in graph.predicate_objects(node)
        ]
        sig = "{" + "|".join(sorted(parts)) + "}"
        content_cache[node] = sig
        return sig

    def path_sig(node: Any) -> str:
        subject, predicate = parents[node]
        base = path_sig(subject) if isinstance(subject, rdflib.BNode) else str(subject.n3())
        return f"{base} {predicate.n3()}"

    # Distinct (path, content) pairs get distinct labels; structurally identical
    # siblings (same path prefix, same content) are disambiguated by a stable
    # index so every blank node ends with a unique N-Triples label.
    keyed: dict[Any, list[Any]] = defaultdict(list)
    for b in bnodes:
        keyed[(path_sig(b), content_sig(b))].append(b)
    labels: dict[Any, Any] = {}
    for i, key in enumerate(sorted(keyed)):
        for j, node in enumerate(keyed[key]):
            labels[node] = rdflib.BNode(f"c{i}x{j}")
    return labels


def _canonicalize_shacl(turtle_text: str) -> str:
    """Byte-stable form of ShaclGenerator output.

    ShaclGenerator is nondeterministic in two validation-irrelevant ways:
    property-shape emission order (blank-node structure) and the element order
    of set-semantics RDF lists (`sh:ignoredProperties`, `sh:in`). It also
    assigns `sh:order` (a SHACL *non-validating* presentation property) from
    that unstable iteration order. Canonical form: drop `sh:order`, sort the
    set-lists, relabel blank nodes canonically, emit sorted N-Triples (a
    Turtle subset, so downstream `format="turtle"` parsers are unaffected).

    Blank-node relabeling uses the forest fast path (`_blank_node_labels`);
    if the graph is not a forest it falls back to rdflib's general
    `to_canonical_graph`, which is correct but O(n) graph-isomorphism work.
    """
    import rdflib
    from rdflib.collection import Collection

    sh = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    graph = rdflib.Graph()
    graph.parse(data=turtle_text, format="turtle")
    graph.remove((None, sh.order, None))
    for pred in (sh.ignoredProperties, sh["in"]):
        for subject, head in list(graph.subject_objects(pred)):
            items = list(Collection(graph, head))
            Collection(graph, head).clear()  # type: ignore[no-untyped-call]
            graph.remove((subject, pred, head))
            new_head = rdflib.BNode()
            Collection(graph, new_head, sorted(items, key=str))
            graph.add((subject, pred, new_head))

    labels = _blank_node_labels(graph)
    if labels is None:
        from rdflib.compare import to_canonical_graph

        emit = to_canonical_graph(graph)
        lines = sorted(line for line in emit.serialize(format="nt").splitlines() if line)
    else:

        def term(node: Any) -> str:
            label = labels[node] if isinstance(node, rdflib.BNode) else node
            return str(label.n3())

        lines = sorted(f"{term(s)} {p.n3()} {term(o)} ." for s, p, o in graph)
    header = [
        "# Auto-generated by scripts/codegen_kg_schema.py — do not edit.",
        "# Canonicalized SHACL shapes (sorted N-Triples; sh:order stripped,",
        "# set-semantics lists sorted) so regeneration is byte-stable.",
    ]
    return "\n".join(header + lines) + "\n"


def gen_shacl(yaml_path: Path, out_path: Path) -> None:
    from linkml.generators.shaclgen import ShaclGenerator

    gen = ShaclGenerator(str(yaml_path))
    out_path.write_text(
        _canonicalize_shacl(_normalize(gen.serialize(), yaml_path)),
        encoding="utf-8",
        newline="\n",
    )


def gen_subclass_axioms(yaml_paths: list[Path], out_path: Path) -> None:
    from cataforge.domain.kg._schema_axioms import iter_subclass_axioms, prefix_map

    namespaces = prefix_map(yaml_paths)
    pairs = list(iter_subclass_axioms(yaml_paths))

    lines: list[str] = [
        "# Auto-generated by scripts/codegen_kg_schema.py — do not edit.",
        "# Materializes the LinkML `is_a` chain as rdfs:subClassOf triples so",
        "# pyoxigraph property-path queries (a/rdfs:subClassOf*) traverse the",
        "# class hierarchy. Loaded by `cataforge kg init` at store bootstrap.",
        "",
    ]
    for prefix in sorted(namespaces):
        lines.append(f"@prefix {prefix}: <{namespaces[prefix]}> .")
    lines.append("")

    for child, parent in pairs:
        lines.append(f"{child} rdfs:subClassOf {parent} .")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def codegen(target_dir: Path) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Path] = []

    py_out = target_dir / "core_pydantic.py"
    ttl_out = target_dir / "core_shapes.ttl"
    gen_pydantic(CORE_YAML, py_out)
    gen_shacl(CORE_YAML, ttl_out)
    artifacts += [py_out, ttl_out]

    subclass_out = target_dir / "subclass_axioms.ttl"
    gen_subclass_axioms([CORE_YAML, GOVERNANCE_YAML], subclass_out)
    artifacts.append(subclass_out)
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LinkML → Pydantic + SHACL + rdfs:subClassOf codegen for cataforge.domain.kg",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="output directory (default: src/cataforge/domain/kg/_generated)",
    )
    args = parser.parse_args(argv)

    for required in (CORE_YAML, GOVERNANCE_YAML):
        if not required.exists():
            print(f"[FAIL] schema source missing: {required}", file=sys.stderr)
            return 1

    artifacts = codegen(args.out)
    for path in artifacts:
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        print(f"[OK] {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
