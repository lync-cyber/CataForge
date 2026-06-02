"""Document / Volume / Section structural ontology (Phase 1 foundation)."""

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


def test_structural_classes_exist_and_are_standalone() -> None:
    sv = _schema_view()
    for name in ("Document", "Volume", "Section"):
        cls = sv.get_class(name)
        assert cls is not None, f"missing class {name}"
        # Structural containers are not business artifacts — like Project,
        # they must not inherit SoftwareArtifact's entity_id/sort_key reqs.
        assert cls.is_a is None, f"{name} must be standalone, got is_a={cls.is_a}"


def test_section_carries_prose_and_entity_containment() -> None:
    sv = _schema_view()
    section_slots = set(sv.class_slots("Section"))
    assert {"narrative_body", "contains_entity", "section_anchor"} <= section_slots


def test_document_and_volume_structure_slots() -> None:
    sv = _schema_view()
    assert {"has_volume", "has_section", "doc_type"} <= set(sv.class_slots("Document"))
    assert {"part_of_document", "has_section", "volume_type"} <= set(sv.class_slots("Volume"))


def test_entities_backlink_to_their_section() -> None:
    sv = _schema_view()
    # located_in_section is inherited by every SoftwareArtifact subclass.
    assert "located_in_section" in set(sv.class_slots("Feature"))


def test_contains_entity_and_located_in_section_are_inverses() -> None:
    sv = _schema_view()
    assert sv.get_slot("contains_entity").inverse == "located_in_section"
    assert sv.get_slot("located_in_section").inverse == "contains_entity"
