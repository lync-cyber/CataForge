"""``cataforge viz`` — render framework / project structure as diagrams.

Text formats only (Mermaid / DOT / JSON) render natively in GitHub / IDEs /
docs sites with zero runtime dependencies. Output goes to stdout by default
(pipe-friendly) or to ``-o PATH``.
"""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.application.viz import service
from cataforge.application.viz.registry import RENDERERS
from cataforge.interface.cli.helpers import resolve_root
from cataforge.interface.cli.main import cli

_FORMATS = sorted(RENDERERS)


def _emit(content: str, output: Path | None) -> None:
    if output is None:
        click.echo(content)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content + "\n")
    click.echo(f"wrote {output}", err=True)


@cli.group("viz")
def viz_group() -> None:
    """Render framework / project structure as diagrams (text formats)."""


@viz_group.command("framework")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(_FORMATS),
    default="mermaid",
    show_default=True,
    help="Output format.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write to PATH instead of stdout.",
)
def viz_framework(fmt: str, output: Path | None) -> None:
    """Orchestrator → phase → agent → skill orchestration graph."""
    _emit(service.generate("framework", fmt, resolve_root()), output)
