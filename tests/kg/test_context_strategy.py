"""context.strategy resolver + context.kg_active_doc_types resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.domain.kg._config import BUSINESS_DOC_TYPES
from cataforge.domain.kg._dispatch import (
    DEFAULT_CONTEXT_STRATEGY,
    active_doc_types,
    context_strategy,
    invalidate_cache,
)


def _write_framework(root: Path, payload: dict) -> None:
    cataforge_dir = root / ".cataforge"
    cataforge_dir.mkdir(parents=True, exist_ok=True)
    (cataforge_dir / "framework.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    yield
    invalidate_cache()


def test_strategy_defaults_to_kg_first_when_absent(tmp_path: Path) -> None:
    _write_framework(tmp_path, {"context": {"kg_active_doc_types": ["prd"]}})
    assert context_strategy(tmp_path) == "kg-first"
    assert DEFAULT_CONTEXT_STRATEGY == "kg-first"


def test_strategy_reads_declared_value(tmp_path: Path) -> None:
    _write_framework(tmp_path, {"context": {"strategy": "doc-only"}})
    assert context_strategy(tmp_path) == "doc-only"


def test_strategy_unrecognized_value_falls_back_to_default(tmp_path: Path) -> None:
    _write_framework(tmp_path, {"context": {"strategy": "nonsense"}})
    assert context_strategy(tmp_path) == "kg-first"


def test_active_doc_types_reads_context_section(tmp_path: Path) -> None:
    _write_framework(tmp_path, {"context": {"kg_active_doc_types": ["prd", "arch"]}})
    assert active_doc_types(tmp_path) == {"prd", "arch"}


def test_active_doc_types_explicit_empty_means_legacy_only(tmp_path: Path) -> None:
    """An explicit empty list means legacy-only, not 'unset'."""
    _write_framework(tmp_path, {"context": {"kg_active_doc_types": []}})
    assert active_doc_types(tmp_path) == set()


def test_active_doc_types_default_when_unset(tmp_path: Path) -> None:
    _write_framework(tmp_path, {"context": {"strategy": "kg-first"}})
    assert active_doc_types(tmp_path) == set(BUSINESS_DOC_TYPES)


def test_active_doc_types_ignores_legacy_kg_section(tmp_path: Path) -> None:
    """The key moved to context — a stray kg-section copy is not read."""
    _write_framework(tmp_path, {"kg": {"kg_active_doc_types": ["prd"]}})
    assert active_doc_types(tmp_path) == set(BUSINESS_DOC_TYPES)
