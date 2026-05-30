"""Schema card for NL→SPARQL grounding (kg-ask skill backing)."""
from __future__ import annotations


def test_card_includes_every_entity_class() -> None:
    from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS
    from cataforge.domain.kg.schema_context import build_schema_card

    card = build_schema_card()
    for klass in ENTITY_PREFIX_TO_CLASS.values():
        assert f"cf:{klass}" in card, f"missing entity class {klass}"


def test_card_includes_every_traceability_predicate() -> None:
    from cataforge.domain.kg.ingest.relation_extract import (
        DEFAULT_PREDICATE,
        PREDICATE_MAP,
    )
    from cataforge.domain.kg.schema_context import build_schema_card

    card = build_schema_card()
    for predicate in set(PREDICATE_MAP.values()) | {DEFAULT_PREDICATE}:
        assert predicate in card, f"missing predicate {predicate}"


def test_card_includes_every_scalar_slot() -> None:
    from cataforge.domain.kg.export.hydrator import _SCALAR_FIELDS
    from cataforge.domain.kg.schema_context import build_schema_card

    card = build_schema_card()
    for field in _SCALAR_FIELDS:
        assert f"cf:{field}" in card, f"missing scalar slot {field}"


def test_card_embeds_namespace_prefix() -> None:
    from cataforge.domain.kg import KGConfig
    from cataforge.domain.kg._sparql_utils import cf_namespace
    from cataforge.domain.kg.schema_context import build_schema_card

    config = KGConfig()
    card = build_schema_card(config)
    assert f"PREFIX cf: <{cf_namespace(config)}>" in card


def test_card_predicate_direction_is_source_to_target() -> None:
    """Page satisfies Feature — direction must read Page -> Feature, not reversed."""
    from cataforge.domain.kg.schema_context import build_schema_card

    card = build_schema_card()
    satisfies_line = next(
        ln for ln in card.splitlines() if ln.startswith("- `cf:satisfies`")
    )
    assert "Page -> Feature" in satisfies_line


def test_card_is_ascii_safe() -> None:
    """The card prints to arbitrary terminals — keep it encodable on cp1252."""
    from cataforge.domain.kg.schema_context import build_schema_card

    build_schema_card().encode("cp1252")
