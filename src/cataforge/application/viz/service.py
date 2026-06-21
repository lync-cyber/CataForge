"""Generate a rendered view, or serve the product directory over HTTP.

``generate`` collects the IR then renders it: ``fmt`` selects a text renderer
(mermaid / dot / json) and the sentinel ``"html"`` routes to the self-contained
HTML renderer; ``dashboard`` is HTML-only and aggregates every viable view.

``serve`` is the tier-3 capability: a standard-library ``http.server`` hosting
the product directory (default ``docs/viz/``). With ``watch`` it polls the
backing data sources' mtimes (KG store / doc-index / EVENT-LOG / CORRECTIONS)
and regenerates the dashboard ``index.html`` when any of them changes. No
third-party dependency is pulled in.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cataforge.application.viz import html
from cataforge.application.viz.registry import COLLECTORS, RENDERERS, collect_safe
from cataforge.core.corrections import CORRECTIONS_LOG_REL
from cataforge.core.errors import CataforgeError
from cataforge.core.event_log import EVENT_LOG_REL
from cataforge.core.paths import KG_STORE_REL
from cataforge.core.viz.model import Graph, MetricSeries, Timeline, is_empty
from cataforge.domain.docs.indexer import INDEX_FILENAME

_HTML = "html"
_INDEX = "index.html"

# viz status readiness states.
READY = "ready"
EMPTY = "empty"
NEEDS_SETUP = "needs-setup"


def generate(view: str, fmt: str, root: Path, /, **opts: Any) -> str:
    if view == "dashboard":
        if fmt != _HTML:
            raise CataforgeError("dashboard view is HTML-only; pass --html")
        return html.render_dashboard(root, **opts)

    collector = COLLECTORS.get(view)
    if collector is None:
        raise CataforgeError(f"unknown viz view: {view!r} (known: {sorted(COLLECTORS)})")
    ir = collector(root, **opts)

    if fmt == _HTML:
        return html.render(ir)
    renderer = RENDERERS.get(fmt)
    if renderer is None:
        raise CataforgeError(f"unknown viz format: {fmt!r} (known: {sorted(RENDERERS)})")
    return renderer(ir)


# --------------------------------------------------------------------------- #
# readiness probe — what can be visualised right now, and what each view needs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ViewStatus:
    """One ``viz status`` row: a view's data-source readiness."""

    name: str
    state: str  # READY | EMPTY | NEEDS_SETUP
    detail: str


def _summary(view: Graph | Timeline | MetricSeries) -> str:
    if isinstance(view, Graph):
        return f"{len(view.nodes)} nodes · {len(view.edges)} edges"
    if isinstance(view, Timeline):
        return f"{len(view.events)} events"
    return f"{len(view.points)} points"


def probe_all(root: Path) -> list[ViewStatus]:
    """Probe every registered view's readiness in registry order. A view is
    ``NEEDS_SETUP`` when its collector cannot reach its data source (the detail
    carries the collector's own ``run …`` hint), ``EMPTY`` when it renders but
    holds no data yet, else ``READY`` with a node/event count."""
    out: list[ViewStatus] = []
    for name in COLLECTORS:
        view, error = collect_safe(root, name)
        if view is None:
            out.append(ViewStatus(name, NEEDS_SETUP, " ".join((error or "").split())))
        elif is_empty(view):
            out.append(ViewStatus(name, EMPTY, view.title or "no data yet"))
        else:
            out.append(ViewStatus(name, READY, _summary(view)))
    return out


# --------------------------------------------------------------------------- #
# tier 3 — local static serve + watch
# --------------------------------------------------------------------------- #
class _QuietHandler(SimpleHTTPRequestHandler):
    """``SimpleHTTPRequestHandler`` without the default per-request stderr log."""

    def log_message(self, *_args: Any) -> None:
        pass


def _watched_paths(root: Path) -> tuple[Path, ...]:
    """The backing data sources whose mtime drives ``--watch`` regeneration."""
    return (
        root / KG_STORE_REL,
        root / "docs" / INDEX_FILENAME,
        root / EVENT_LOG_REL,
        root / CORRECTIONS_LOG_REL,
    )


def _mtime(path: Path) -> float:
    """Latest mtime for *path*: a directory (e.g. the KG store) folds to the
    newest mtime among its files; a missing path contributes ``0.0``."""
    if path.is_dir():
        return max((p.stat().st_mtime for p in path.rglob("*") if p.is_file()), default=0.0)
    if path.is_file():
        return path.stat().st_mtime
    return 0.0


def _fingerprint(root: Path) -> tuple[float, ...]:
    """A change-detection tuple of every watched source's mtime."""
    return tuple(_mtime(p) for p in _watched_paths(root))


def regenerate(root: Path, serve_dir: Path) -> Path:
    """(Re)write the dashboard into ``serve_dir/index.html``. The dashboard
    degrades failed views to error panels, so it renders for any project
    state — there is always something to serve."""
    serve_dir.mkdir(parents=True, exist_ok=True)
    index = serve_dir / _INDEX
    index.write_text(generate("dashboard", _HTML, root))
    return index


def _regenerate_if_changed(
    root: Path, serve_dir: Path, last: tuple[float, ...]
) -> tuple[float, ...]:
    """Regenerate when any watched source's mtime differs from *last*; return
    the current fingerprint either way."""
    current = _fingerprint(root)
    if current != last:
        regenerate(root, serve_dir)
    return current


def _watch_loop(
    root: Path,
    serve_dir: Path,
    stop: threading.Event,
    interval: float,
    log: Callable[[str], None] | None,
) -> None:
    last = _fingerprint(root)
    while not stop.wait(interval):
        try:
            current = _regenerate_if_changed(root, serve_dir, last)
        except Exception as exc:  # a transient read must never kill the watcher
            if log is not None:
                log(f"regenerate failed: {exc}")
            continue
        if current != last and log is not None:
            log(f"regenerated {serve_dir / _INDEX}")
        last = current


def _build_server(serve_dir: Path, host: str, port: int) -> ThreadingHTTPServer:
    handler = functools.partial(_QuietHandler, directory=str(serve_dir))
    return ThreadingHTTPServer((host, port), handler)


def serve(
    root: Path,
    /,
    *,
    directory: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    watch: bool = False,
    poll_interval: float = 1.0,
    stop: threading.Event | None = None,
    on_ready: Callable[[ThreadingHTTPServer], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    """Serve *serve_dir* (default ``docs/viz/``) over a local static server and
    block until interrupted. ``watch`` starts a background thread that
    regenerates the dashboard when a backing source changes.

    *stop* lets a caller request shutdown from another thread (tests / signals);
    omitted, the loop runs until ``KeyboardInterrupt``. *on_ready* receives the
    bound server once it is accepting connections; *log* receives status lines.
    """
    serve_dir = (Path(directory) if directory else root / "docs" / "viz").resolve()
    regenerate(root, serve_dir)
    try:
        httpd = _build_server(serve_dir, host, port)
    except OSError as exc:
        raise CataforgeError(f"cannot bind {host}:{port} — {exc}") from exc

    stop = stop or threading.Event()
    threads = [threading.Thread(target=httpd.serve_forever, name="viz-serve", daemon=True)]
    if watch:
        threads.append(
            threading.Thread(
                target=_watch_loop,
                args=(root, serve_dir, stop, poll_interval, log),
                name="viz-watch",
                daemon=True,
            )
        )
    for thread in threads:
        thread.start()

    if log is not None:
        bound = httpd.server_address[1]
        log(f"serving {serve_dir} at http://{host}:{bound}/  (Ctrl-C to stop)")
    if on_ready is not None:
        on_ready(httpd)

    try:
        while not stop.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.shutdown()
        httpd.server_close()
        for thread in threads:
            thread.join(timeout=5)
