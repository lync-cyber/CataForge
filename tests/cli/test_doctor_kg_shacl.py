"""Doctor `KG SHACL conformance` gate: OK / violation / degrade-loudly paths."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"

_HAS_SHACL = (
    importlib.util.find_spec("pyshacl") is not None
    and importlib.util.find_spec("rdflib") is not None
)


@dataclass
class _FakePaths:
    root: Path


@dataclass
class _FakeCfg:
    paths: _FakePaths


def _project_with_store(tmp_path: Path, *, seed_fixture: bool) -> _FakeCfg:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    cfg = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
    )
    handle = init_store(cfg, force=True)
    if seed_fixture:
        run_migration(handle.raw, FIXTURE_ROOT / "waterfall", cfg)
    handle.raw.flush()
    handle.close()
    return _FakeCfg(paths=_FakePaths(root=proj))


def test_no_store_skips(tmp_path: Path) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_shacl_conformance

    cfg = _FakeCfg(paths=_FakePaths(root=tmp_path))
    assert check_kg_shacl_conformance(cfg) == 0


@pytest.mark.skipif(not _HAS_SHACL, reason="shacl extra not installed")
def test_conforming_store_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import gc

    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_shacl_conformance

    cfg = _project_with_store(tmp_path, seed_fixture=True)
    gc.collect()
    assert check_kg_shacl_conformance(cfg) == 0
    assert "conforms" in capsys.readouterr().out


@pytest.mark.skipif(not _HAS_SHACL, reason="shacl extra not installed")
def test_nonconforming_store_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An entity violating a required-slot shape must gate the doctor run."""
    import gc

    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_shacl_conformance

    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    kg_cfg = KGConfig(store_backend="oxigraph", db_path=proj / ".cataforge" / "kg" / "store")
    handle = init_store(kg_cfg, force=True)
    ns = kg_cfg.ontology_namespace.rstrip("/") + "/"
    inst = kg_cfg.base_namespace.rstrip("/") + "/"
    string_dt = ox.NamedNode("http://www.w3.org/2001/XMLSchema#string")
    subject = ox.NamedNode(f"{inst}T-001")
    # A Task missing required sort_key/content_hash and carrying an
    # out-of-enum task_status — multiple shape violations.
    handle.raw.add(
        ox.Quad(
            subject,
            ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            ox.NamedNode(f"{ns}Task"),
        )
    )
    handle.raw.add(
        ox.Quad(subject, ox.NamedNode(f"{ns}entity_id"), ox.Literal("T-001", datatype=string_dt))
    )
    handle.raw.add(
        ox.Quad(subject, ox.NamedNode(f"{ns}task_status"), ox.Literal("doing", datatype=string_dt))
    )
    handle.raw.flush()
    handle.close()
    gc.collect()

    cfg = _FakeCfg(paths=_FakePaths(root=proj))
    assert check_kg_shacl_conformance(cfg) == 1
    assert "SHACL violation" in capsys.readouterr().out


def test_missing_deps_degrade_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the shacl extra the check prints a skip note — never silent."""
    import gc

    from cataforge.domain.kg import validate as validate_mod
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_shacl_conformance

    cfg = _project_with_store(tmp_path, seed_fixture=False)
    gc.collect()
    monkeypatch.setattr(validate_mod, "_find_shapes_file", lambda: None)
    assert check_kg_shacl_conformance(cfg) == 0
    out = capsys.readouterr().out
    assert "skipped" in out
    assert "shacl" in out.lower()
