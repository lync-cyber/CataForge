"""The split-Volume graph layer is removed: one logical Document → Section."""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("linkml_runtime") is None,
    reason="linkml_runtime not installed (KG ontology extra)",
)


def _schema_view():
    from linkml_runtime.utils.schemaview import SchemaView

    from cataforge.domain.kg._schema_axioms import schema_paths

    return SchemaView(str(schema_paths()[0]))


def test_volume_class_is_gone() -> None:
    sv = _schema_view()
    assert sv.get_class("Volume") is None


def test_volume_slots_are_gone() -> None:
    sv = _schema_view()
    for slot in ("has_volume", "part_of_volume", "volume_type"):
        assert sv.get_slot(slot) is None, f"slot {slot} must be removed"


def test_document_has_no_volume_link() -> None:
    sv = _schema_view()
    assert "has_volume" not in set(sv.class_slots("Document"))


def test_section_belongs_only_to_document() -> None:
    sv = _schema_view()
    section_slots = set(sv.class_slots("Section"))
    assert "part_of_document" in section_slots
    assert "part_of_volume" not in section_slots
