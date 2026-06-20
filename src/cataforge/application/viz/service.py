"""Generate a rendered view: collect the IR, then render it to text or HTML.

``fmt`` selects a text renderer (mermaid / dot / json); the sentinel ``"html"``
routes to the self-contained HTML renderer instead. ``dashboard`` is HTML-only:
it aggregates every viable view into one tabbed page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.application.viz import html
from cataforge.application.viz.registry import COLLECTORS, RENDERERS
from cataforge.core.errors import CataforgeError

_HTML = "html"


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
