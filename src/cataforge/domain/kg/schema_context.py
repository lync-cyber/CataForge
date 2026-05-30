"""Schema card for natural-language → SPARQL grounding.

`build_schema_card(config)` assembles a compact, LLM-facing description of
the knowledge graph: entity classes, traceability predicates, scalar slots,
and worked read-only query examples. A host agent embeds this card alongside
a user's natural-language question to emit a valid SPARQL query, which then
runs through `cataforge kg query` (write-guarded, LIMIT-injected).

The card is derived from the live registries (`ENTITY_PREFIX_TO_CLASS`,
`PREDICATE_MAP`, the hydrator scalar set) so it never drifts from the
ingest/export code.
"""

from __future__ import annotations

from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._sparql_utils import cf_namespace
from cataforge.domain.kg.export.hydrator import _SCALAR_FIELDS
from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS
from cataforge.domain.kg.ingest.relation_extract import DEFAULT_PREDICATE, PREDICATE_MAP


def _entity_class_rows() -> list[tuple[str, str]]:
    """Return (prefix, class) pairs sorted by class name."""
    return sorted(ENTITY_PREFIX_TO_CLASS.items(), key=lambda kv: kv[1])


def _predicate_semantics() -> dict[str, list[tuple[str, str]]]:
    """Invert PREDICATE_MAP to predicate → [(source_class, target_class)]."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for (src_class, tgt_prefix), predicate in PREDICATE_MAP.items():
        tgt_class = ENTITY_PREFIX_TO_CLASS.get(tgt_prefix, tgt_prefix)
        grouped.setdefault(predicate, []).append((src_class, tgt_class))
    for pairs in grouped.values():
        pairs.sort()
    return grouped


def _examples(ns: str) -> list[tuple[str, str]]:
    """Return (intent, sparql) example pairs grounded on namespace `ns`."""
    prefix = f"PREFIX cf: <{ns}>"
    return [
        (
            "List every feature with its title",
            f"{prefix}\n"
            "SELECT ?id ?title WHERE {\n"
            "  ?f a cf:Feature ; cf:entity_id ?id ; cf:title ?title\n"
            "} ORDER BY ?id",
        ),
        (
            "Which tasks satisfy acceptance criterion AC-001",
            f"{prefix}\n"
            "SELECT ?task WHERE {\n"
            "  ?t a cf:Task ; cf:satisfies ?ac ; cf:entity_id ?task .\n"
            '  ?ac cf:entity_id "AC-001"\n'
            "}",
        ),
        (
            "Features with no verifying test case (coverage gap)",
            f"{prefix}\n"
            "SELECT ?id WHERE {\n"
            "  ?f a cf:Feature ; cf:entity_id ?id .\n"
            "  FILTER NOT EXISTS { ?tc cf:verifies ?f }\n"
            "} ORDER BY ?id",
        ),
    ]


def build_schema_card(config: KGConfig | None = None) -> str:
    """Assemble the schema card markdown for the given (or default) config."""
    config = config or KGConfig()
    ns = cf_namespace(config)

    lines: list[str] = []
    lines.append("# Knowledge Graph Schema")
    lines.append("")
    lines.append("Read-only SPARQL over the project knowledge graph. Always start a")
    lines.append(f"query with `PREFIX cf: <{ns}>` and type entities via `?x a cf:<Class>`.")
    lines.append("Entities carry `cf:entity_id` (e.g. `F-001`) and `cf:title`.")
    lines.append("")

    lines.append("## Entity classes")
    lines.append("")
    lines.append("| id prefix | class |")
    lines.append("|-----------|-------|")
    for prefix, klass in _entity_class_rows():
        lines.append(f"| `{prefix}-NNN` | `cf:{klass}` |")
    lines.append("")

    lines.append("## Traceability predicates")
    lines.append("")
    lines.append("Direction is `source -predicate-> target`.")
    lines.append("")
    for predicate in sorted(_predicate_semantics()):
        pairs = _predicate_semantics()[predicate]
        rendered = ", ".join(f"{src} -> {tgt}" for src, tgt in pairs)
        lines.append(f"- `{predicate}`: {rendered}")
    lines.append(f"- `{DEFAULT_PREDICATE}`: fallback edge for any unmapped reference")
    lines.append("")

    lines.append("## Scalar slots")
    lines.append("")
    lines.append("Each entity may carry these `cf:` literal slots:")
    lines.append("")
    lines.append(", ".join(f"`cf:{field}`" for field in _SCALAR_FIELDS))
    lines.append("")

    lines.append("## Example queries")
    lines.append("")
    for intent, sparql in _examples(ns):
        lines.append(f"**{intent}**")
        lines.append("")
        lines.append("```sparql")
        lines.append(sparql)
        lines.append("```")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
