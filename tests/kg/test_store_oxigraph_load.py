"""Oxigraph load() path smoke test — skipped when pyoxigraph is not installed."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pyoxigraph") is None,
    reason="pyoxigraph not installed",
)

from cataforge.kg.store import StoreError, Triple  # noqa: E402
from cataforge.kg.store_oxigraph import OxigraphStore  # noqa: E402


def _project(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_load_nquads_file_populates_store(tmp_path: Path) -> None:
    nq_file = tmp_path / "seed.nq"
    nq_file.write_text(
        "<https://example.org/s> <https://example.org/p>"
        ' "hello" <https://example.org/g> .\n',
        encoding="utf-8",
    )

    project = _project(tmp_path / "proj")
    store = OxigraphStore()
    store.load(project)

    import pyoxigraph as _pyoxi

    store._oxi.load(path=str(nq_file), format=_pyoxi.RdfFormat.N_QUADS)

    rows = store.query(
        "SELECT ?s WHERE { GRAPH <https://example.org/g>"
        " { ?s <https://example.org/p> ?o } }",
    )
    assert len(rows) == 1
    assert rows[0]["s"] == "https://example.org/s"


def test_snapshot_file_raises_without_load() -> None:
    store = OxigraphStore()
    with pytest.raises(StoreError, match="project_root"):
        store._snapshot_file()


def test_persist_without_load_raises() -> None:
    store = OxigraphStore()
    with pytest.raises(StoreError):
        store.persist()


def test_full_roundtrip(tmp_path: Path) -> None:
    project = _project(tmp_path)
    store = OxigraphStore()
    store.load(project)
    store.add([Triple("cfa:prd/F-oxi-001", "rdf:type", "cfa:Feature")])
    store.add([Triple("cfa:prd/F-oxi-001", "rdfs:label", "oxi-smoke")])

    rows = store.query(
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "SELECT ?lbl WHERE { ?s rdfs:label ?lbl }",
    )
    assert len(rows) == 1
    assert rows[0]["lbl"] == "oxi-smoke"

    store.persist()
    snapshot = project / "docs" / ".doc-graph" / "oxigraph" / "snapshot.nq"
    assert snapshot.is_file()
    content = snapshot.read_text(encoding="utf-8")
    assert "oxi-smoke" in content
