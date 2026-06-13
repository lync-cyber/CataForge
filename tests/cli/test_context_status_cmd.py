"""`cataforge context status` — read-only backend probe."""

from __future__ import annotations

import gc
import json
import shutil
from pathlib import Path

import pytest

from cataforge.interface.cli.context_cmd import context_status
from tests.cli.conftest import invoke_under_group

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


@pytest.fixture(autouse=True)
def _isolate_cache():
    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    yield
    invalidate_cache()


def _kg_first_project(tmp_path: Path) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"strategy": "kg-first"}}), encoding="utf-8"
    )
    return proj


def test_status_uninitialized_store_reports_false_without_creating(tmp_path: Path) -> None:
    proj = _kg_first_project(tmp_path)
    store_dir = proj / ".cataforge" / "kg" / "store"
    assert not store_dir.exists()

    result = invoke_under_group(context_status, ["--project-root", str(proj)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "strategy": "kg-first",
        "authoring": "md",
        "store_initialized": False,
        "entity_count": 0,
    }
    # Probing must not create the store directory.
    assert not store_dir.exists()


def test_status_initialized_store_reports_entity_count(tmp_path: Path) -> None:
    from cataforge.domain.kg import init_store
    from cataforge.domain.kg._dispatch import invalidate_cache, kg_config_for
    from cataforge.domain.kg.ingest import run_migration

    proj = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT / "waterfall", proj)
    (proj / ".cataforge").mkdir(exist_ok=True)
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"strategy": "kg-first"}}), encoding="utf-8"
    )
    cfg = kg_config_for(proj)
    handle = init_store(cfg, force=True)
    run_migration(handle.raw, proj, cfg)
    del handle
    gc.collect()
    invalidate_cache()

    result = invoke_under_group(context_status, ["--project-root", str(proj)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["strategy"] == "kg-first"
    assert payload["authoring"] == "md"
    assert payload["store_initialized"] is True
    assert payload["entity_count"] > 0


def test_status_reports_graph_authoring(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"strategy": "kg-first", "authoring": "graph"}}),
        encoding="utf-8",
    )

    result = invoke_under_group(context_status, ["--project-root", str(proj)])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["authoring"] == "graph"
