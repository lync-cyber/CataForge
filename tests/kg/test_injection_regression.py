"""Integration regression tests for SPARQL / IRI injection hardening.

Unit-level escape behavior is covered in ``test_sparql_escape.py``.
This file covers the wired call-sites: the escape utilities are
actually invoked at the boundaries that previously did naked f-string
interpolation, and adversarial inputs no longer break SPARQL parsing.
"""
from __future__ import annotations

import pytest

from cataforge.domain.kg._sparql_utils import (
    assert_safe_iri,
    escape_iri_component,
)
from cataforge.domain.kg.ingest.iri import class_iri, entity_iri


class TestEntityIriEncoding:
    """``entity_iri`` / ``class_iri`` percent-encode user-controlled segments."""

    def test_plain_id_unchanged(self) -> None:
        assert entity_iri("F-001") == "https://cataforge.dev/instance/F-001"

    def test_space_percent_encoded(self) -> None:
        iri = entity_iri("F-001 leak")
        assert iri == "https://cataforge.dev/instance/F-001%20leak"
        assert_safe_iri(iri)

    def test_angle_bracket_in_id_cannot_escape_boundary(self) -> None:
        iri = entity_iri("F>injected")
        assert "%3E" in iri
        assert ">" not in iri
        assert_safe_iri(iri)

    def test_quote_in_id_encoded(self) -> None:
        iri = entity_iri('F"-001')
        assert '"' not in iri
        assert_safe_iri(iri)

    def test_unicode_class_name_encoded(self) -> None:
        iri = class_iri("中文Class")
        assert "%E4%B8%AD" in iri
        assert_safe_iri(iri)


class TestContentHashGuard:
    """``writer._content_hash_matches`` rejects non-SHA-hex inputs."""

    def test_invalid_hex_rejected(self) -> None:
        from cataforge.domain.kg.ingest.writer import _content_hash_matches

        # SHA-256 hex is 64 lowercase hex chars; anything else is bogus.
        with pytest.raises(ValueError, match="invalid content_hash format"):
            _content_hash_matches(
                None,  # type: ignore[arg-type]
                "https://example.com/F-001",
                "not-a-hash",
                namespace="https://cataforge.dev/ontology/",
            )

    def test_uppercase_hex_rejected(self) -> None:
        """SHA-256 ``hashlib.sha256().hexdigest()`` is lowercase; uppercase
        is non-canonical input and the guard refuses it."""
        from cataforge.domain.kg.ingest.writer import _content_hash_matches

        upper = "A" * 64
        with pytest.raises(ValueError, match="invalid content_hash format"):
            _content_hash_matches(
                None,  # type: ignore[arg-type]
                "https://example.com/F-001",
                upper,
                namespace="https://cataforge.dev/ontology/",
            )

    def test_short_hex_rejected(self) -> None:
        from cataforge.domain.kg.ingest.writer import _content_hash_matches

        with pytest.raises(ValueError, match="invalid content_hash format"):
            _content_hash_matches(
                None,  # type: ignore[arg-type]
                "https://example.com/F-001",
                "abc123",
                namespace="https://cataforge.dev/ontology/",
            )


class TestAssertSafeIriAtBoundary:
    """The transaction / verify / writer layers reject IRIs that would
    break the ``<...>`` boundary in SPARQL.

    A direct unit test of ``assert_safe_iri`` already exists; this
    confirms the helper is the *correct* shape for use at SPARQL
    boundaries (no false positives on conformant IRIs we produce
    ourselves).
    """

    def test_iris_produced_by_entity_iri_pass(self) -> None:
        for raw in ["F-001", "AC-123", "API-007", "TS_-001"]:
            iri = entity_iri(raw)
            assert_safe_iri(iri)

    def test_iris_produced_by_class_iri_pass(self) -> None:
        for cls in ["Feature", "AcceptanceCriteria", "TestSuite"]:
            iri = class_iri(cls)
            assert_safe_iri(iri)


class TestEscapeIriComponentRoundTrip:
    """End-to-end: encode → wrap in ``<...>`` → still a single token."""

    @pytest.mark.parametrize(
        "raw",
        [
            "F-001",
            "F with space",
            "F<inject>",
            "F#fragment",
            "F?query=1",
            "中文 ID",
        ],
    )
    def test_wrap_yields_single_iri_token(self, raw: str) -> None:
        encoded = escape_iri_component(raw)
        wrapped = f"<https://example.com/{encoded}>"
        assert wrapped.count("<") == 1
        assert wrapped.count(">") == 1
