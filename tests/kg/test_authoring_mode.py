"""`authoring_mode` accessor — kg-first/graph gating and md default."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.domain.kg._dispatch import authoring_mode, invalidate_cache


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


def test_default_is_md_when_unset(tmp_path: Path) -> None:
    proj = _project(tmp_path, {"strategy": "kg-first"})
    assert authoring_mode(proj) == "md"


def test_explicit_graph_under_kg_first(tmp_path: Path) -> None:
    proj = _project(tmp_path, {"strategy": "kg-first", "authoring": "graph"})
    assert authoring_mode(proj) == "graph"


def test_explicit_md_under_kg_first(tmp_path: Path) -> None:
    proj = _project(tmp_path, {"strategy": "kg-first", "authoring": "md"})
    assert authoring_mode(proj) == "md"


def test_unrecognized_value_falls_back_to_md(tmp_path: Path) -> None:
    proj = _project(tmp_path, {"strategy": "kg-first", "authoring": "bogus"})
    assert authoring_mode(proj) == "md"


def test_doc_only_project_is_always_md(tmp_path: Path) -> None:
    # Even an explicit graph request has no graph authority under doc-only.
    proj = _project(tmp_path, {"strategy": "doc-only", "authoring": "graph"})
    assert authoring_mode(proj) == "md"


def test_missing_framework_json_defaults_md(tmp_path: Path) -> None:
    proj = tmp_path / "bare"
    proj.mkdir()
    assert authoring_mode(proj) == "md"
