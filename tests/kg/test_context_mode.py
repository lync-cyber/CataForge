"""`context_mode` accessor and `kg_enabled` derivation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.domain.kg._dispatch import context_mode, invalidate_cache, kg_enabled


@pytest.fixture(autouse=True)
def _isolate_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def _project(tmp_path: Path, context: dict[str, str]) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": context}), encoding="utf-8"
    )
    return proj


@pytest.mark.parametrize("mode", ["markdown", "graph"])
def test_explicit_mode_is_honoured(tmp_path: Path, mode: str) -> None:
    assert context_mode(_project(tmp_path, {"mode": mode})) == mode


def test_default_is_graph_when_unset(tmp_path: Path) -> None:
    assert context_mode(_project(tmp_path, {})) == "graph"


def test_unrecognized_value_falls_back_to_graph(tmp_path: Path) -> None:
    # The retired ``hybrid`` value is unrecognized now, so it resolves to graph.
    assert context_mode(_project(tmp_path / "a", {"mode": "hybrid"})) == "graph"
    assert context_mode(_project(tmp_path / "b", {"mode": "bogus"})) == "graph"


def test_legacy_strategy_authoring_are_not_read(tmp_path: Path) -> None:
    # Hard cutover: the retired axes are ignored, so a project still carrying
    # them resolves to the graph default (the doctor flags the stale schema).
    proj = _project(tmp_path, {"strategy": "doc-only", "authoring": "graph"})
    assert context_mode(proj) == "graph"


def test_missing_framework_json_defaults_graph(tmp_path: Path) -> None:
    proj = tmp_path / "bare"
    proj.mkdir()
    assert context_mode(proj) == "graph"


@pytest.mark.parametrize(
    "mode,enabled",
    [("markdown", False), ("graph", True)],
)
def test_kg_enabled_tracks_mode(tmp_path: Path, mode: str, enabled: bool) -> None:
    assert kg_enabled(_project(tmp_path, {"mode": mode})) is enabled
