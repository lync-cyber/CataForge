"""FidelityRouter — operation × strategy × availability matrix + integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.domain.context.ports import (
    OP_DEPS,
    OP_READ_SECTION,
    Fidelity,
)
from cataforge.domain.context.router import FidelityRouter, build_router

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


class _FakeBackend:
    def __init__(self, name: str, fidelity: dict[str, Fidelity], result):
        self.name = name
        self.fidelity = fidelity
        self._result = result
        self.calls: list[str] = []

    def read_section(self, ref, project_root, *, file_cache=None):
        self.calls.append("read_section")
        return self._result

    def deps(self, ref, project_root, max_depth):
        self.calls.append("deps")
        return self._result


# ---- ordering / availability ------------------------------------------------


def test_orders_by_fidelity_highest_first() -> None:
    low = _FakeBackend("low", {OP_DEPS: Fidelity.DEGRADED}, ["x"])
    high = _FakeBackend("high", {OP_DEPS: Fidelity.NATIVE}, ["y"])
    router = FidelityRouter([low, high])  # insertion order low, high
    assert router.deps("r", ".", 2) == ["y"]  # high (native) consulted first
    assert high.calls and not low.calls


def test_unsupported_backend_is_skipped() -> None:
    unsup = _FakeBackend("unsup", {OP_READ_SECTION: Fidelity.UNSUPPORTED}, "nope")
    doc = _FakeBackend("doc", {OP_READ_SECTION: Fidelity.NATIVE}, "ok")
    router = FidelityRouter([unsup, doc])
    assert router.read_section("r", ".") == "ok"
    assert not unsup.calls


def test_falls_through_when_higher_backend_returns_none() -> None:
    kg = _FakeBackend("kg", {OP_READ_SECTION: Fidelity.NATIVE}, None)
    doc = _FakeBackend("doc", {OP_READ_SECTION: Fidelity.NATIVE}, "from-doc")
    router = FidelityRouter([kg, doc])
    assert router.read_section("r", ".") == "from-doc"
    assert kg.calls == ["read_section"] and doc.calls == ["read_section"]


def test_higher_backend_short_circuits() -> None:
    kg = _FakeBackend("kg", {OP_READ_SECTION: Fidelity.NATIVE}, "from-kg")
    doc = _FakeBackend("doc", {OP_READ_SECTION: Fidelity.NATIVE}, "from-doc")
    router = FidelityRouter([kg, doc])
    assert router.read_section("r", ".") == "from-kg"
    assert not doc.calls  # not consulted once kg served


def test_deps_returns_empty_when_all_decline() -> None:
    kg = _FakeBackend("kg", {OP_DEPS: Fidelity.NATIVE}, None)
    doc = _FakeBackend("doc", {OP_DEPS: Fidelity.DEGRADED}, None)
    assert FidelityRouter([kg, doc]).deps("r", ".", 2) == []


# ---- build_router topology by strategy --------------------------------------


def _write_strategy(root: Path, strategy: str) -> None:
    (root / ".cataforge").mkdir(parents=True, exist_ok=True)
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"strategy": strategy}}), encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def _clear_dispatch_cache():
    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    yield
    invalidate_cache()


def test_build_router_kg_first_enables_both(tmp_path: Path) -> None:
    _write_strategy(tmp_path, "kg-first")
    names = [b.name for b in build_router(str(tmp_path))._backends]
    assert names == ["kg", "doc"]


def test_build_router_doc_only_enables_file_alone(tmp_path: Path) -> None:
    _write_strategy(tmp_path, "doc-only")
    names = [b.name for b in build_router(str(tmp_path))._backends]
    assert names == ["doc"]


# ---- integration: strategy actually changes the resolving backend ----------


def _kg_project(tmp_path: Path, strategy: str) -> Path:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    project = tmp_path / "project"
    (project / ".cataforge").mkdir(parents=True)
    import shutil

    shutil.copytree(FIXTURE_ROOT / "waterfall" / "docs", project / "docs")
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test-report"},
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, project, config)
    handle.raw.flush()
    handle.close()
    ctx = {"strategy": strategy, "kg_active_doc_types": ["prd", "arch", "test-report"]}
    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": ctx}), encoding="utf-8"
    )
    return project


def test_doc_only_never_serves_pure_prose_from_kg(tmp_path: Path) -> None:
    """arch#§1 (no entity) only resolves via the graph; doc-only must NOT
    serve it from KG — proving the strategy gates the backend topology."""
    from cataforge.domain.docs import loader
    from cataforge.domain.docs.index_ops import SectionNotFoundError

    project = _kg_project(tmp_path, "kg-first")
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()
    assert "概览" in loader.extract("arch#§1", str(project))  # kg-first serves it

    from cataforge.domain.kg._dispatch import invalidate_cache

    project2 = _kg_project(tmp_path / "b", "doc-only")
    invalidate_cache()
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()
    with pytest.raises(SectionNotFoundError):
        loader.extract("arch#§1", str(project2))  # file backend can't match §1
