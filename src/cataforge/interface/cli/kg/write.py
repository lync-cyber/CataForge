"""cataforge kg entity mutations — add, update, delete."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.domain.kg import KnowledgeGraph

from cataforge.core.errors import (
    CataforgeError,
    KGStoreError,
)
from cataforge.interface.cli.kg import kg_group
from cataforge.interface.cli.kg._options import db_path_ro_option


def _parse_kv_pairs(pairs: tuple[str, ...], flag_name: str) -> dict[str, str]:
    """Parse repeatable ``--flag KEY=VALUE`` options into a dict."""
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise CataforgeError(f"{flag_name} expects KEY=VALUE, got: {raw}")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise CataforgeError(f"{flag_name} key may not be empty: {raw}")
        out[key] = value
    return out


def _resolve_project_iri(
    kg: KnowledgeGraph,
    project_id: str | None,
    *,
    project_title: str | None,
    project_process_model: str,
) -> str:
    """Resolve the parent project IRI for entity writes.

    Resolution order:
    1. If ``project_id`` is given, idempotently materialize that Project
       node (creating it if missing) and return its IRI.
    2. Otherwise query the store for an existing ``cf:Project`` instance
       — if exactly one exists, use it.
    3. Otherwise raise: caller must pick.
    """
    from cataforge.domain.kg._sparql_utils import cf_namespace  # noqa: PLC0415
    from cataforge.domain.kg.ingest.iri import class_iri
    from cataforge.domain.kg.ingest.writer import write_project

    config = kg.config
    namespace = cf_namespace(config)

    if project_id is not None:
        title = project_title or project_id
        return write_project(kg.store, project_id, title, project_process_model, config)

    sparql = f"SELECT ?p WHERE {{ ?p a <{class_iri('Project', namespace)}> }} LIMIT 2"
    raw = kg.store.query(sparql)
    project_iris: list[str] = []
    for row in raw:  # type: ignore[union-attr]
        try:
            term = row["p"]
        except (KeyError, IndexError):
            continue
        project_iris.append(getattr(term, "value", str(term)))

    if len(project_iris) == 1:
        return project_iris[0]
    if len(project_iris) == 0:
        raise CataforgeError(
            "No cf:Project node found in store. "
            "Pass --project-id to create one (and --project-title / "
            "--project-process to set its metadata)."
        )
    raise CataforgeError(
        f"Multiple cf:Project nodes found in store ({len(project_iris)}+). "
        "Pass --project-id to disambiguate."
    )


@kg_group.command("add")
@click.argument("entity_id")
@click.option(
    "--class",
    "class_name",
    required=True,
    help="Schema class name (e.g. Feature, Module, Component, TestCase).",
)
@click.option(
    "--title",
    required=True,
    help="Human-readable title for the entity.",
)
@click.option(
    "--source-doc",
    default="",
    show_default=False,
    help="Originating doc_id (e.g. 'prd'). Empty string allowed for synthetic entities.",
)
@click.option(
    "--source-section",
    default="",
    show_default=False,
    help="Originating section heading. Defaults to ENTITY_ID + title.",
)
@click.option(
    "--content-hash",
    default=None,
    help=(
        "Content hash for idempotency. Default: sha256 of '{source_doc}|{source_section}|{title}'."
    ),
)
@click.option(
    "--project-id",
    default=None,
    help=(
        "Project entity_id for the cf:in_project edge. "
        "If omitted, the store's unique Project node is auto-detected."
    ),
)
@click.option(
    "--project-title",
    default=None,
    help="Project title — only used when --project-id materializes a new node.",
)
@click.option(
    "--project-process",
    type=click.Choice(["waterfall", "agile"]),
    default="waterfall",
    show_default=True,
    help="Project process_model — only used when --project-id materializes a new node.",
)
@click.option(
    "--slot",
    "slots",
    multiple=True,
    help="Extra slot in KEY=VALUE form. Repeatable. KEY may use 'cf:' prefix.",
)
@click.option(
    "--relation",
    "relations",
    multiple=True,
    help="Outgoing edge in PREDICATE=OBJECT_ID form. Repeatable.",
)
@db_path_ro_option()
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON status blob instead of the human-readable line.",
)
def kg_add(
    entity_id: str,
    class_name: str,
    title: str,
    source_doc: str,
    source_section: str,
    content_hash: str | None,
    project_id: str | None,
    project_title: str | None,
    project_process: str,
    slots: tuple[str, ...],
    relations: tuple[str, ...],
    db_path: Path,
    json_output: bool,
) -> None:
    """Add a new entity (and optional outgoing edges) to the KG.

    Idempotent: re-running with an unchanged --content-hash is a no-op.
    Re-running with a changed hash replaces the entity's quads atomically.
    """
    import hashlib

    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph

    slot_dict = _parse_kv_pairs(slots, "--slot")
    relation_dict = _parse_kv_pairs(relations, "--relation")

    effective_section = source_section or f"{entity_id} {title}"
    if content_hash is None:
        payload = f"{source_doc}|{effective_section}|{title}".encode()
        content_hash = hashlib.sha256(payload).hexdigest()

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraph.connect(config) as kg:
            project_iri = _resolve_project_iri(
                kg,
                project_id,
                project_title=project_title,
                project_process_model=project_process,
            )
            with kg.transaction() as txn:
                iri = txn.add_entity(
                    entity_id=entity_id,
                    class_name=class_name,
                    title=title,
                    source_doc=source_doc,
                    source_section=effective_section,
                    content_hash=content_hash,
                    project_iri=project_iri,
                    extra_slots=slot_dict or None,
                )
                added_relations = 0
                for predicate, object_id in relation_dict.items():
                    before = txn.pending_inserts
                    txn.add_relation(entity_id, predicate, object_id)
                    if txn.pending_inserts > before:
                        added_relations += 1
                inserts = txn.pending_inserts
                deletes = txn.pending_deletes
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "entity_id": entity_id,
                    "iri": iri,
                    "class": class_name,
                    "content_hash": content_hash,
                    "pending_inserts": inserts,
                    "pending_deletes": deletes,
                    "relations_added": added_relations,
                },
                indent=2,
            )
        )
    else:
        verb = "added" if inserts > 0 else "unchanged"
        click.echo(
            f"OK: {entity_id} {verb} ({inserts} inserts, {deletes} deletes, "
            f"{added_relations}/{len(relation_dict)} relations)"
        )
        click.echo(f"  iri: {iri}")


@kg_group.command("update")
@click.argument("entity_id")
@click.option("--title", default=None, help="New title.")
@click.option("--source-section", default=None, help="New source_section heading.")
@click.option(
    "--slot",
    "slots",
    multiple=True,
    help="Slot update in KEY=VALUE form. Repeatable.",
)
@click.option(
    "--content-hash",
    default=None,
    help=(
        "New content_hash. Idempotent: if the entity already carries this "
        "hash, the update is skipped."
    ),
)
@db_path_ro_option()
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON status blob instead of the human-readable line.",
)
def kg_update(
    entity_id: str,
    title: str | None,
    source_section: str | None,
    slots: tuple[str, ...],
    content_hash: str | None,
    db_path: Path,
    json_output: bool,
) -> None:
    """Update slots on an existing entity. Raises if the entity is absent."""
    from cataforge.domain.kg import (
        KGConfig,
        KGEntityNotFoundError,
        KGStoreNotInitializedError,
        KnowledgeGraph,
    )

    slot_dict = _parse_kv_pairs(slots, "--slot")
    if title is not None:
        slot_dict.setdefault("title", title)
    if source_section is not None:
        slot_dict.setdefault("source_section", source_section)

    if not slot_dict and content_hash is None:
        raise CataforgeError(
            "kg update requires at least one of: --title, --source-section, "
            "--slot KEY=VALUE, --content-hash."
        )

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraph.connect(config) as kg, kg.transaction() as txn:
            try:
                txn.update_entity(entity_id, content_hash=content_hash, **slot_dict)
            except KGEntityNotFoundError as exc:
                raise KGStoreError(str(exc)) from exc
            inserts = txn.pending_inserts
            deletes = txn.pending_deletes
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "entity_id": entity_id,
                    "slots_updated": sorted(slot_dict.keys()),
                    "content_hash_set": content_hash is not None,
                    "pending_inserts": inserts,
                    "pending_deletes": deletes,
                },
                indent=2,
            )
        )
    else:
        if inserts == 0 and deletes == 0:
            click.echo(f"OK: {entity_id} unchanged (content_hash matched).")
        else:
            click.echo(f"OK: {entity_id} updated ({inserts} inserts, {deletes} deletes)")


@kg_group.command("delete")
@click.argument("entity_id")
@click.option(
    "--cascade",
    is_flag=True,
    default=False,
    help="Also remove incoming edges. Without it, refuses if any exist.",
)
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip the interactive confirmation prompt.",
)
@db_path_ro_option()
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON status blob instead of the human-readable line.",
)
def kg_delete(
    entity_id: str,
    cascade: bool,
    yes: bool,
    db_path: Path,
    json_output: bool,
) -> None:
    """Remove an entity (and optionally its incoming edges) from the KG."""
    from cataforge.domain.kg import (
        KGConfig,
        KGEntityNotFoundError,
        KGStoreNotInitializedError,
        KGValidationError,
        KnowledgeGraph,
    )

    if not yes:
        suffix = " (and incoming edges)" if cascade else ""
        if not click.confirm(f"Delete {entity_id}{suffix}?", default=False):
            click.echo("Aborted.")
            return

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraph.connect(config) as kg, kg.transaction() as txn:
            try:
                txn.delete_entity(entity_id, cascade=cascade)
            except KGEntityNotFoundError as exc:
                raise KGStoreError(str(exc)) from exc
            except KGValidationError as exc:
                raise KGStoreError(
                    f"{exc}\nHint: pass --cascade to remove incoming edges too."
                ) from exc
            deletes = txn.pending_deletes
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "entity_id": entity_id,
                    "cascade": cascade,
                    "pending_deletes": deletes,
                },
                indent=2,
            )
        )
    else:
        click.echo(
            f"OK: {entity_id} deleted ({deletes} quads removed{', cascade' if cascade else ''})."
        )
