"""Shared fixtures for the kg test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from rdflib import Graph

from cataforge.kg.ontology import load_ontology, load_shapes
from cataforge.kg.store import RDFLibStore


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """A throwaway project root with the expected ``docs/`` subdir."""
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture
def empty_store(tmp_project: Path) -> Iterator[RDFLibStore]:
    """A fresh :class:`RDFLibStore` already bound to ``tmp_project``."""
    store = RDFLibStore()
    store.load(tmp_project)
    yield store


@pytest.fixture(scope="session")
def builtin_ontology(tmp_path_factory: pytest.TempPathFactory) -> Graph:
    """The combined L0+L1+L2 ontology graph, loaded once per session."""
    return load_ontology(
        tmp_path_factory.mktemp("ontology_root"),
        include_l3=False,
        strict=True,
    )


@pytest.fixture(scope="session")
def builtin_shapes(tmp_path_factory: pytest.TempPathFactory) -> Graph:
    """The combined SHACL shape graph (kernel + process + artifact)."""
    return load_shapes(
        tmp_path_factory.mktemp("shapes_root"),
        include_l3=False,
        strict=True,
    )
