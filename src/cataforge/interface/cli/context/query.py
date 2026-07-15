"""cataforge context read-only probes — read, status."""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.interface.cli.context import context_group
from cataforge.interface.cli.context._shared import _kg_store_guard, _rooted


@context_group.command("read")
@click.argument("refs", nargs=-1, required=True)
@click.option("--project-root", default=None)
@click.option("--json", "json_output", is_flag=True)
@click.option("--with-deps", is_flag=True)
@click.option("--budget", type=int, default=None)
@click.pass_context
def context_read(
    ctx: click.Context,
    refs: tuple[str, ...],
    project_root: str | None,
    json_output: bool,
    with_deps: bool,
    budget: int | None,
) -> None:
    """Mode-routed section read of ``doc_id#§N[.item]`` REFS."""
    from cataforge.interface.cli._support.doc_io import run_load

    run_load(
        refs,
        _rooted(ctx, project_root),
        json_output,
        with_deps,
        budget,
        command_label="context read",
    )


@context_group.command("status")
@click.option("--project-root", default=None)
@click.option("--json", "json_output", is_flag=True, help="Emit a JSON probe instead of text.")
@click.pass_context
def context_status(ctx: click.Context, project_root: str, json_output: bool) -> None:
    """Print a read-only probe of the project's context backend.

    Reports the resolved ``context.mode`` and, when a graph store is already on
    disk, its entity count. Defaults to a human-readable summary; ``--json``
    emits the machine-readable blob. Probing never creates the store: an
    uninitialized project reads ``store_initialized: false`` with a zero count,
    leaving disk untouched.
    """
    import json

    from cataforge.domain.kg._dispatch import context_mode

    project_root = _rooted(ctx, project_root)
    store_dir = Path(project_root) / ".cataforge" / "kg" / "store"
    payload: dict[str, object] = {
        "mode": context_mode(project_root),
        "store_initialized": store_dir.exists(),
        "entity_count": 0,
    }
    if store_dir.exists():
        from cataforge.domain.kg import KnowledgeGraph
        from cataforge.domain.kg._dispatch import kg_config_for

        cfg = kg_config_for(project_root)
        with _kg_store_guard(), KnowledgeGraph.connect(cfg, read_only=True) as kg:
            payload["entity_count"] = len(kg.query.entity_ids())
    if json_output:
        click.echo(json.dumps(payload))
        return
    click.echo(f"mode: {payload['mode']}")
    click.echo(f"store_initialized: {str(payload['store_initialized']).lower()}")
    click.echo(f"entity_count: {payload['entity_count']}")
