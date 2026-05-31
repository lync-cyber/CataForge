"""Tests for override-layer resolution (core.layers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.core.layers import asset_layer_dirs, has_overrides
from cataforge.core.paths import ProjectPaths


def _mk(root: Path, rel: str) -> Path:
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_asset_layer_dirs_orders_low_to_high(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    scaffold = _mk(tmp_path, ".cataforge/agents")
    project = _mk(tmp_path, ".cataforge/overrides/project/agents")
    user = _mk(tmp_path, ".cataforge/overrides/user/agents")

    assert asset_layer_dirs(paths, "agents") == [scaffold, project, user]


def test_asset_layer_dirs_skips_absent(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    scaffold = _mk(tmp_path, ".cataforge/skills")
    # Only the user layer exists besides scaffold.
    user = _mk(tmp_path, ".cataforge/overrides/user/skills")

    assert asset_layer_dirs(paths, "skills") == [scaffold, user]


def test_has_overrides(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    _mk(tmp_path, ".cataforge")
    assert has_overrides(paths) is False
    _mk(tmp_path, ".cataforge/overrides")
    assert has_overrides(paths) is True


def test_unknown_kind_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown asset kind"):
        asset_layer_dirs(ProjectPaths(tmp_path), "widgets")
