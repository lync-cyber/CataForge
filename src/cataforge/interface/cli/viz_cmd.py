"""``cataforge viz`` — render framework / project structure as diagrams.

Text formats (Mermaid / DOT / JSON) render natively in GitHub / IDEs / docs
sites with zero runtime dependencies. ``--html`` instead emits a single
self-contained offline page (Cytoscape.js for graphs, ECharts for charts);
it overrides ``--format``. Output goes to stdout by default (pipe-friendly)
or to ``-o PATH``.
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
_HTML = "html"

F = TypeVar("F", bound=Callable[..., Any])


def _format_option(fn: F) -> F:
    return click.option(
        "--format",
        "fmt",
        type=click.Choice(_FORMATS),
        default="mermaid",
        show_default=True,
        help="Text output format.",
    )(fn)


def _html_option(fn: F) -> F:
    return click.option(
        "--html",
        "as_html",
        is_flag=True,
        default=False,
        help="Emit a self-contained offline HTML page (overrides --format).",
    )(fn)


def _output_option(fn: F) -> F:
    return click.option(
        "-o",
        "--output",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help="Write to PATH instead of stdout.",
    )(fn)


def _render_options(fn: F) -> F:
    return _format_option(_html_option(_output_option(fn)))


def _emit(content: str, output: Path | None) -> None:
    if output is None:
        click.echo(content)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content + "\n")
    click.echo(f"wrote {output}", err=True)


def _run(view: str, fmt: str, as_html: bool, output: Path | None, **opts: Any) -> None:
    content = service.generate(view, _HTML if as_html else fmt, resolve_root(), **opts)
    _emit(content, output)


@cli.group("viz")
def viz_group() -> None:
    """Render framework / project structure as diagrams (text or HTML)."""


@viz_group.command("framework")
@_render_options
def viz_framework(fmt: str, as_html: bool, output: Path | None) -> None:
    """Orchestrator → phase → agent → skill orchestration graph."""
    _run("framework", fmt, as_html, output)


@viz_group.command("assets")
@_render_options
def viz_assets(fmt: str, as_html: bool, output: Path | None) -> None:
    """Agent / skill asset graph with a search box (best with --html)."""
    _run("assets", fmt, as_html, output)


@viz_group.command("trace")
@click.argument("entity_id", required=False, default=None)
@click.option(
    "--direction",
    type=click.Choice(["downstream", "upstream", "both"]),
    default="downstream",
    show_default=True,
    help="Chain traversal direction.",
)
@_render_options
def viz_trace(
    entity_id: str | None, direction: str, fmt: str, as_html: bool, output: Path | None
) -> None:
    """Traceability graph. Omit ENTITY_ID to aggregate every Feature."""
    _run("trace", fmt, as_html, output, entity_id=entity_id, direction=direction)


@viz_group.command("coverage")
@_render_options
def viz_coverage(fmt: str, as_html: bool, output: Path | None) -> None:
    """Feature coverage matrix: nodes styled by impl/test status."""
    _run("coverage", fmt, as_html, output)


@viz_group.command("arch")
@_render_options
def viz_arch(fmt: str, as_html: bool, output: Path | None) -> None:
    """Architecture graph: Module/Component/API/DataModel + depends_on edges."""
    _run("arch", fmt, as_html, output)


@viz_group.command("docs")
@_render_options
def viz_docs(fmt: str, as_html: bool, output: Path | None) -> None:
    """Document dependency graph: stale / broken upstreams highlighted."""
    _run("docs", fmt, as_html, output)


@viz_group.command("tasks")
@click.option("--edges", default="", help='Task edges: "T-001→T-002,T-002→T-003".')
@click.option("--weights", default="", help='Task weights: "T-001:S,T-002:M".')
@_render_options
def viz_tasks(edges: str, weights: str, fmt: str, as_html: bool, output: Path | None) -> None:
    """Task dependency graph: critical path / cycle nodes highlighted.

    With --edges, renders that DAG; without it, reads Task.depends_on from the KG.
    """
    _run("tasks", fmt, as_html, output, edges=edges, weights=weights)


@viz_group.command("phase")
@_render_options
def viz_phase(fmt: str, as_html: bool, output: Path | None) -> None:
    """SDLC phase backbone; current phase green (gate ok) or red (blocked)."""
    _run("phase", fmt, as_html, output)


@viz_group.command("timeline")
@_render_options
def viz_timeline(fmt: str, as_html: bool, output: Path | None) -> None:
    """EVENT-LOG timeline: events grouped by date."""
    _run("timeline", fmt, as_html, output)


@viz_group.command("decay")
@_render_options
def viz_decay(fmt: str, as_html: bool, output: Path | None) -> None:
    """CORRECTIONS-LOG decay timeline: one event per correction."""
    _run("decay", fmt, as_html, output)


@viz_group.command("dashboard")
@_output_option
def viz_dashboard(output: Path | None) -> None:
    """Aggregate every viable view into one tabbed offline HTML page."""
    _emit(service.generate("dashboard", _HTML, resolve_root()), output)
