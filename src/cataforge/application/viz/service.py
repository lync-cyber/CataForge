"""Generate a rendered view: collect the IR, then render it to text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.application.viz.registry import COLLECTORS, RENDERERS
from cataforge.core.errors import CataforgeError


def generate(view: str, fmt: str, root: Path, /, **opts: Any) -> str:
    collector = COLLECTORS.get(view)
    if collector is None:
        raise CataforgeError(f"unknown viz view: {view!r} (known: {sorted(COLLECTORS)})")
    renderer = RENDERERS.get(fmt)
    if renderer is None:
        raise CataforgeError(f"unknown viz format: {fmt!r} (known: {sorted(RENDERERS)})")
    return renderer(collector(root, **opts))
