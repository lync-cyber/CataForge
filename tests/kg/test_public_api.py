"""Smoke tests for the cataforge.domain.kg public API surface."""
from __future__ import annotations


def test_render_entity_importable_from_top_level() -> None:
    from cataforge.domain.kg import render_entity

    assert callable(render_entity)


def test_all_exports_are_importable() -> None:
    import cataforge.domain.kg as kg

    for name in kg.__all__:
        assert hasattr(kg, name), f"missing export: {name}"
