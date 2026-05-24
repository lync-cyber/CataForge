"""triples_from_schema — agent output → triples mapping contract.

Covers:
* required vs optional literal fields
* literal-field dict form ({"field": "x", "optional": true})
* iri_ref string-template substitution against item + context
* iri_ref dict form, including list values (multi-edge fan-out)
* explicit failure modes (missing key, bad type, malformed schema)
"""

from __future__ import annotations

from typing import Any

import pytest

from cataforge.kg.adapters import AdapterError, triples_from_schema
from cataforge.kg.store import Triple

# ----- basic shape -----

def test_minimal_feature_shape() -> None:
    schema: dict[str, Any] = {
        "items": [
            {
                "from": "features",
                "iri": "cfa:${doc_id}/${id}",
                "type": "cfa:Feature",
                "literals": {"rdfs:label": "label", "cfk:hasId": "id"},
                "iri_refs": {"cfk:definedIn": "cfk:doc/${doc_id}"},
            }
        ]
    }
    output: dict[str, Any] = {
        "doc_id": "prd-acme",
        "features": [{"id": "F-001", "label": "Login"}],
    }
    triples = triples_from_schema(output, schema)
    assert Triple("cfa:prd-acme/F-001", "rdf:type", "cfa:Feature") in triples
    assert Triple("cfa:prd-acme/F-001", "cfk:hasId", "F-001") in triples
    assert Triple("cfa:prd-acme/F-001", "rdfs:label", "Login") in triples
    assert Triple(
        "cfa:prd-acme/F-001", "cfk:definedIn", "cfk:doc/prd-acme",
    ) in triples


# ----- optional / required -----

def test_optional_literal_skipped_when_missing() -> None:
    schema: dict[str, Any] = {
        "items": [
            {
                "from": "features",
                "iri": "cfa:doc/${id}",
                "type": "cfa:Feature",
                "literals": {
                    "cfk:hasId": "id",
                    "cfa:status": {"field": "status", "optional": True},
                },
            }
        ]
    }
    output = {"features": [{"id": "F-001"}]}
    triples = triples_from_schema(output, schema)
    assert all(t.p != "cfa:status" for t in triples)


def test_required_literal_missing_raises() -> None:
    schema: dict[str, Any] = {
        "items": [
            {
                "from": "features",
                "iri": "cfa:doc/${id}",
                "type": "cfa:Feature",
                "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
            }
        ]
    }
    output = {"features": [{"id": "F-001"}]}  # no label
    with pytest.raises(AdapterError) as exc:
        triples_from_schema(output, schema)
    assert "label" in str(exc.value)


# ----- iri_refs -----

def test_iri_ref_dict_field_form() -> None:
    schema: dict[str, Any] = {
        "items": [
            {
                "from": "modules",
                "iri": "cfa:arch/${id}",
                "type": "cfa:Module",
                "literals": {"cfk:hasId": "id"},
                "iri_refs": {
                    "cfa:implements": {"field": "implements", "as_iri": True},
                },
            }
        ]
    }
    output = {
        "modules": [{
            "id": "M-001",
            "implements": "cfa:prd/F-001",
        }],
    }
    triples = triples_from_schema(output, schema)
    assert Triple(
        "cfa:arch/M-001", "cfa:implements", "cfa:prd/F-001",
    ) in triples


def test_iri_ref_list_fans_out_to_multiple_triples() -> None:
    schema: dict[str, Any] = {
        "items": [
            {
                "from": "modules",
                "iri": "cfa:arch/${id}",
                "type": "cfa:Module",
                "literals": {"cfk:hasId": "id"},
                "iri_refs": {
                    "cfa:implements": {"field": "implements", "as_iri": True},
                },
            }
        ]
    }
    output = {
        "modules": [{
            "id": "M-001",
            "implements": ["cfa:prd/F-001", "cfa:prd/F-002"],
        }],
    }
    triples = triples_from_schema(output, schema)
    impl = [t for t in triples if t.p == "cfa:implements"]
    assert len(impl) == 2
    assert {t.o for t in impl} == {"cfa:prd/F-001", "cfa:prd/F-002"}


def test_iri_ref_optional_missing_is_skipped() -> None:
    schema: dict[str, Any] = {
        "items": [
            {
                "from": "modules",
                "iri": "cfa:arch/${id}",
                "type": "cfa:Module",
                "literals": {"cfk:hasId": "id"},
                "iri_refs": {
                    "cfa:implements": {
                        "field": "implements", "optional": True,
                    },
                },
            }
        ]
    }
    output = {"modules": [{"id": "M-001"}]}
    triples = triples_from_schema(output, schema)
    assert all(t.p != "cfa:implements" for t in triples)


def test_iri_ref_required_missing_raises() -> None:
    schema: dict[str, Any] = {
        "items": [
            {
                "from": "modules",
                "iri": "cfa:arch/${id}",
                "type": "cfa:Module",
                "literals": {"cfk:hasId": "id"},
                "iri_refs": {
                    "cfa:implements": {"field": "implements"},
                },
            }
        ]
    }
    output = {"modules": [{"id": "M-001"}]}
    with pytest.raises(AdapterError):
        triples_from_schema(output, schema)


# ----- malformed schema / output -----

def test_items_must_be_list() -> None:
    with pytest.raises(AdapterError):
        triples_from_schema({"x": []}, {"items": "not-a-list"})


def test_missing_required_decl_keys() -> None:
    with pytest.raises(AdapterError) as exc:
        triples_from_schema(
            {"x": [{}]}, {"items": [{"from": "x"}]},
        )
    assert "iri" in str(exc.value) or "type" in str(exc.value)


def test_source_key_must_be_list() -> None:
    schema = {
        "items": [{
            "from": "modules",
            "iri": "cfa:m/${id}",
            "type": "cfa:Module",
            "literals": {"cfk:hasId": "id"},
        }]
    }
    with pytest.raises(AdapterError):
        triples_from_schema({"modules": {"not": "a list"}}, schema)


def test_missing_source_key_treated_as_empty_list() -> None:
    schema = {
        "items": [{
            "from": "modules",
            "iri": "cfa:m/${id}",
            "type": "cfa:Module",
            "literals": {"cfk:hasId": "id"},
        }]
    }
    triples = triples_from_schema({}, schema)
    assert triples == []
