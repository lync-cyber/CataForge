"""Unit tests for :mod:`cataforge.kg.viz` traversal correctness."""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.kg.store import RDFLibStore, Triple
from cataforge.kg.viz import _rows_from_root


@pytest.fixture
def chain_store(tmp_path: Path) -> RDFLibStore:
    """A → B → C → D chain (4 nodes, 3 hops)."""
    (tmp_path / "docs").mkdir()
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfa:m/A", "cfa:dependsOn", "cfa:m/B"),
        Triple("cfa:m/B", "cfa:dependsOn", "cfa:m/C"),
        Triple("cfa:m/C", "cfa:dependsOn", "cfa:m/D"),
    ])
    return store


def _reachable_nodes(rows: list[dict[str, str]]) -> set[str]:
    nodes: set[str] = set()
    for r in rows:
        nodes.add(r["src"])
        nodes.add(r["dst"])
    return nodes


def test_depth_zero_yields_no_rows(chain_store: RDFLibStore) -> None:
    rows = _rows_from_root(chain_store, "cfa:m/A", 0)
    assert rows == []


def test_depth_one_yields_exactly_one_hop(chain_store: RDFLibStore) -> None:
    rows = _rows_from_root(chain_store, "cfa:m/A", 1)
    assert len(rows) == 1
    nodes = _reachable_nodes(rows)
    assert any("m/B" in n for n in nodes)
    assert not any("m/C" in n for n in nodes)


def test_depth_two_yields_exactly_two_hops(chain_store: RDFLibStore) -> None:
    rows = _rows_from_root(chain_store, "cfa:m/A", 2)
    assert len(rows) == 2
    nodes = _reachable_nodes(rows)
    assert any("m/C" in n for n in nodes)
    assert not any("m/D" in n for n in nodes), (
        "depth=2 must not traverse 3 hops"
    )
