"""``cataforge viz`` — render framework / project structure as diagrams.

Text formats only (Mermaid / DOT / JSON) render natively in GitHub / IDEs /
docs sites with zero runtime dependencies. Output goes to stdout by default
(pipe-friendly) or to ``-o PATH``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from cataforge.application.viz import service
from cataforge.application.viz.registry import RENDERERS
from cataforge.interface.cli.helpers import resolve_root
from cataforge.interface.cli.main import cli

_FORMATS = sorted(RENDERERS)

F = TypeVar("F", bound=Callable[..., Any])


def _format_option(fn: F) -> F:
    return click.option(
        "--format",
        "fmt",
        type=click.Choice(_FORMATS),
        default="mermaid",
        show_default=True,
        help="Output format.",
    )(fn)


def _output_option(fn: F) -> F:
    return click.option(
        "-o",
        "--output",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help="Write to PATH instead of stdout.",
    )(fn)


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
@_format_option
@_output_option
def viz_framework(fmt: str, output: Path | None) -> None:
    """Orchestrator → phase → agent → skill orchestration graph."""
    _emit(service.generate("framework", fmt, resolve_root()), output)


@viz_group.command("trace")
@click.argument("entity_id", required=False, default=None)
@click.option(
    "--direction",
    type=click.Choice(["downstream", "upstream", "both"]),
    default="downstream",
    show_default=True,
    help="Chain traversal direction.",
)
@_format_option
@_output_option
def viz_trace(entity_id: str | None, direction: str, fmt: str, output: Path | None) -> None:
    """Traceability graph. Omit ENTITY_ID to aggregate every Feature."""
    content = service.generate(
        "trace", fmt, resolve_root(), entity_id=entity_id, direction=direction
    )
    _emit(content, output)


@viz_group.command("coverage")
@_format_option
@_output_option
def viz_coverage(fmt: str, output: Path | None) -> None:
    """Feature coverage matrix: nodes styled by impl/test status."""
    _emit(service.generate("coverage", fmt, resolve_root()), output)


@viz_group.command("arch")
@_format_option
@_output_option
def viz_arch(fmt: str, output: Path | None) -> None:
    """Architecture graph: Module/Component/API/DataModel + depends_on edges."""
    _emit(service.generate("arch", fmt, resolve_root()), output)
