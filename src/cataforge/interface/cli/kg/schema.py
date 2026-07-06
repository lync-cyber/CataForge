"""cataforge kg schema-context — emit the schema card for NL→SPARQL grounding."""

from __future__ import annotations

import click

from cataforge.interface.cli.kg import kg_group


@kg_group.command("schema-context")
def kg_schema_context() -> None:
    """Print the knowledge-graph schema card.

    The card lists entity classes, traceability predicates, scalar slots, and
    read-only query examples — enough context to translate a natural-language
    question into a SPARQL query for `cataforge kg query`. The card is static
    (derived from the ontology registries) and needs no initialized store.
    """
    from cataforge.core.paths import find_project_root
    from cataforge.domain.kg import KGConfig
    from cataforge.domain.kg._dispatch import custom_entity_prefixes
    from cataforge.domain.kg.schema_context import build_schema_card

    try:
        custom = custom_entity_prefixes(find_project_root())
    except Exception:  # noqa: BLE001 — schema card is static; registration is best-effort
        custom = {}
    click.echo(build_schema_card(KGConfig(), custom_prefixes=custom))
