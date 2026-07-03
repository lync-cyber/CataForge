"""``cataforge viz`` — render framework / project structure as diagrams.

Text formats (Mermaid / DOT / JSON) render natively in GitHub / IDEs / docs
sites with zero runtime dependencies. ``--html`` instead emits a single
self-contained offline page (Cytoscape.js for graphs, ECharts for charts);
it overrides ``--format``. Output goes to stdout by default (pipe-friendly)
or to ``-o PATH``.

``viz status`` reports which views have data right now; ``viz quickstart`` is
the one-command path to a live local dashboard.
"""

from __future__ import annotations

import contextlib
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from cataforge.application.viz import service
from cataforge.application.viz.registry import RENDERERS, short_hint
from cataforge.core.viz.model import is_empty
from cataforge.interface.cli.helpers import resolve_root
from cataforge.interface.cli.main import cli
from cataforge.interface.cli.ui import NextStep, ui

_FORMATS = sorted(RENDERERS)
_HTML = "html"
_QUICKSTART = NextStep(
    "cataforge viz quickstart", "一键起本地实时 dashboard（生成+服务+开浏览器+刷新）"
)
_EPILOG = (
    "Quickstart: `cataforge viz quickstart` 一键起实时 dashboard · "
    "`cataforge viz status` 看哪些视图现在有数据。"
)

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
    # The file is written; nudge toward the interactive view (stderr-only, so
    # piped stdout output stays clean).
    ui.next_steps([_QUICKSTART])


def _run(view: str, fmt: str, as_html: bool, output: Path | None, **opts: Any) -> None:
    ir = service.collect(view, resolve_root(), **opts)
    if is_empty(ir):
        click.echo(f"({view} 视图暂无数据 — `cataforge viz status` 查看各视图就绪状态)", err=True)
    _emit(service.render_view(ir, _HTML if as_html else fmt), output)


def _browser_opener(host: str) -> Callable[[Any], None]:
    """An ``on_ready`` callback that opens the served page once bound. Binds to
    127.0.0.1 in the URL when the server listens on a wildcard address."""
    open_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host

    def _open(httpd: Any) -> None:
        url = f"http://{open_host}:{httpd.server_address[1]}/"
        with contextlib.suppress(Exception):  # opening a browser is best-effort
            webbrowser.open(url)

    return _open


def _serve(directory: Path | None, host: str, port: int, watch: bool, open_browser: bool) -> None:
    service.serve(
        resolve_root(),
        directory=directory,
        host=host,
        port=port,
        watch=watch,
        on_ready=_browser_opener(host) if open_browser else None,
        log=lambda msg: click.echo(msg, err=True),
    )


@cli.group("viz", epilog=_EPILOG)
def viz_group() -> None:
    """Render framework / project structure as diagrams (text or HTML)."""


@viz_group.command("overview")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(_FORMATS),
    default="json",
    show_default=True,
    help="Text output format (metric points have no Mermaid form, so json is the default).",
)
@_html_option
@_output_option
def viz_overview(fmt: str, as_html: bool, output: Path | None) -> None:
    """Project health KPIs: phase/gate, core docs, coverage, links, decay."""
    _run("overview", fmt, as_html, output)


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
@click.option(
    "--open/--no-open",
    "open_browser",
    default=False,
    help="Open the written page in a browser (defaults output to docs/viz/dashboard.html).",
)
def viz_dashboard(output: Path | None, open_browser: bool) -> None:
    """Aggregate every viable view into one tabbed offline HTML page."""
    if open_browser and output is None:
        output = resolve_root() / "docs" / "viz" / "dashboard.html"
    _emit(service.generate("dashboard", _HTML, resolve_root()), output)
    if open_browser and output is not None:
        with contextlib.suppress(Exception):  # best-effort
            webbrowser.open(output.resolve().as_uri())


def _serve_options(fn: F) -> F:
    fn = click.option(
        "--port", type=int, default=8000, show_default=True, help="Port to listen on."
    )(fn)
    fn = click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind.")(fn)
    return click.option(
        "--dir",
        "directory",
        type=click.Path(file_okay=False, path_type=Path),
        default=None,
        help="Directory to serve (default: docs/viz/).",
    )(fn)


@viz_group.command("serve")
@_serve_options
@click.option(
    "--watch",
    is_flag=True,
    default=False,
    help="Regenerate the dashboard when KG / doc-index / EVENT-LOG / CORRECTIONS change.",
)
@click.option(
    "--open/--no-open", "open_browser", default=False, help="Open the served page in a browser."
)
def viz_serve(
    directory: Path | None, host: str, port: int, watch: bool, open_browser: bool
) -> None:
    """Serve the product directory over a local static server (Ctrl-C to stop).

    Writes a dashboard ``index.html`` up front, then hosts the directory with the
    standard library only. With --watch, source-data changes trigger a rebuild.
    """
    _serve(directory, host, port, watch, open_browser)


@viz_group.command("quickstart")
@_serve_options
def viz_quickstart(directory: Path | None, host: str, port: int) -> None:
    """One command to a live dashboard: build + serve + open browser + watch.

    Equivalent to ``viz serve --watch --open`` (Ctrl-C to stop).
    """
    _serve(directory, host, port, watch=True, open_browser=True)


_STATE_LABEL = {service.READY: "ready", service.EMPTY: "empty", service.NEEDS_SETUP: "needs setup"}


@viz_group.command("status")
def viz_status() -> None:
    """Show which views have data right now and what each one still needs."""
    rows = [
        [
            st.name,
            _STATE_LABEL.get(st.state, st.state),
            short_hint(st.detail) if st.state == service.NEEDS_SETUP else st.detail,
        ]
        for st in service.probe_all(resolve_root())
    ]
    ui.table(["view", "state", "detail"], rows)
    ui.next_steps([_QUICKSTART])
