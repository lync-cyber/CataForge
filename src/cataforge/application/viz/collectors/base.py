"""The collector contract — a function ``(root, **opts) -> View``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from cataforge.core.viz.model import View


class Collector(Protocol):
    def __call__(self, root: Path, /, **opts: Any) -> View: ...
