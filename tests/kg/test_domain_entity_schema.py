"""The bounded downstream escape hatch: `DomainEntity` + `DomainAttribute`.

core stays a closed 40-class ontology; one open class lets a downstream domain
project register custom entity prefixes (see O2) so an unregistered prefix is a
signal rather than a silent drop.
"""

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


def test_domain_entity_class_exists_under_software_artifact() -> None:
    sv = _schema_view()
    cls = sv.get_class("DomainEntity")
    assert cls is not None
    assert cls.is_a == "SoftwareArtifact"


def test_domain_entity_carries_domain_type_and_attributes() -> None:
    sv = _schema_view()
    slots = set(sv.class_slots("DomainEntity"))
    assert {"domain_type", "has_attribute", "satisfies"} <= slots
    # domain_type is the required discriminator (which registered domain class).
    assert sv.induced_slot("domain_type", "DomainEntity").required is True


def test_domain_entity_id_pattern_is_permissive() -> None:
    # Unlike core classes (^F-, ^M-, …), a DomainEntity accepts any uppercase
    # prefix — the concrete prefix set is gated at extraction by the registry.
    sv = _schema_view()
    pattern = sv.induced_slot("entity_id", "DomainEntity").pattern
    assert pattern == "^[A-Z]+-[0-9]{3,}$"


def test_domain_attribute_class_holds_key_value() -> None:
    sv = _schema_view()
    cls = sv.get_class("DomainAttribute")
    assert cls is not None
    slots = set(sv.class_slots("DomainAttribute"))
    assert {"attr_name", "attr_value"} <= slots


def test_has_attribute_ranges_over_domain_attribute() -> None:
    sv = _schema_view()
    assert sv.get_slot("has_attribute").range == "DomainAttribute"
    assert sv.get_slot("has_attribute").multivalued is True
