"""Tests for `cataforge.domain.kg.models.to_model` — the typed view over
QueryAPI dict records, backed by the LinkML-generated Pydantic models.

End-to-end coverage ingests the shared vertical-slice fixture and feeds a real
`QueryAPI.feature()` dict through `to_model`, so any drift between the dict
shape and the generated model surfaces. Unit coverage pins the degrade paths
(no record / models unavailable / unknown class) and the `extra="forbid"`
field filter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _open_and_ingest(variant: str):
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    return KnowledgeGraph(handle.raw, config), config


def test_to_model_none_record_returns_none() -> None:
    from cataforge.domain.kg.models import to_model

    assert to_model(None) is None


def test_to_model_degrades_when_models_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from cataforge.domain.kg import models

    monkeypatch.setattr(models, "_MODELS_AVAILABLE", False)
    record = {
        "uri": "https://cataforge.dev/instance/F-001",
        "_class": "Feature",
        "entity_id": "F-001",
    }
    assert models.to_model(record) is None


def test_to_model_unknown_class_returns_none() -> None:
    from cataforge.domain.kg.models import models_available, to_model

    if not models_available():
        pytest.skip("generated pydantic models not importable")
    record = {
        "uri": "https://cataforge.dev/instance/Z-001",
        "_class": "NoSuchClass",
        "entity_id": "Z-001",
    }
    assert to_model(record) is None


def test_to_model_filters_unknown_keys() -> None:
    """A record carrying non-slot keys must not trip the model's extra="forbid"."""
    from cataforge.domain.kg.models import models_available, to_model

    if not models_available():
        pytest.skip("generated pydantic models not importable")
    record = {
        "uri": "https://cataforge.dev/instance/F-001",
        "_class": "Feature",
        "entity_id": "F-001",
        "sort_key": "F:000001",
        "title": "Login flow",
        "nonexistent_slot": "should be dropped",
    }
    model = to_model(record)
    assert model is not None
    assert model.entity_id == "F-001"
    assert model.id == "https://cataforge.dev/instance/F-001"


def test_feature_query_dict_builds_typed_model() -> None:
    from cataforge.domain.kg.models import models_available, to_model

    if not models_available():
        pytest.skip("generated pydantic models not importable")
    kg, _ = _open_and_ingest("waterfall")
    record = kg.query.feature("F-001")
    assert record is not None

    model = to_model(record)
    assert model is not None
    assert type(model).__name__ == "Feature"
    assert model.entity_id == "F-001"
    assert model.title == record["title"]
    assert model.id == record["uri"]
