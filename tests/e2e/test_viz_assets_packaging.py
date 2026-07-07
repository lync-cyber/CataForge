"""The vendored viz JS must ship inside the built wheel.

``html.render`` inlines ``cytoscape.min.js`` / ``echarts.min.js`` resolved via
``importlib.resources``; if hatchling drops them from the wheel, ``--html`` dies
at runtime for installed users. This builds a real wheel and asserts both assets
are packed with their full content.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

_ASSET_PREFIX = "cataforge/application/viz/assets/"
_EXPECTED = {
    f"{_ASSET_PREFIX}cytoscape.min.js": 100_000,
    f"{_ASSET_PREFIX}echarts.min.js": 500_000,
    f"{_ASSET_PREFIX}dashboard.js": 3_000,
    f"{_ASSET_PREFIX}dashboard.css": 1_000,
}


def test_vendored_js_packed_in_wheel(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as wheel:
        names = set(wheel.namelist())
        for member, min_size in _EXPECTED.items():
            assert member in names, f"{member} missing from wheel ({built_wheel.name})"
            assert wheel.getinfo(member).file_size > min_size, f"{member} packed but truncated"
