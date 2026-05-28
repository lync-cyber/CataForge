"""Tests for SPARQL literal / IRI escape utilities.

These cover the fuzz surface that the KG layer exposes: any value reaching
``escape_sparql_literal`` may originate from user-provided frontmatter,
arbitrary markdown text, or chained agent output. Tests assert both
*safety* (no character can escape the literal boundary) and *round-trip*
(escaped output parsed back yields the original value).
"""
from __future__ import annotations

import re

import pytest

from cataforge.kg._sparql_utils import (
    assert_safe_iri,
    escape_iri_component,
    escape_sparql_literal,
)


class TestEscapeSparqlLiteral:
    """``escape_sparql_literal`` — SPARQL ``"..."`` body escape."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", ""),
            ("plain text", "plain text"),
            ("F-001", "F-001"),
            ('with "quotes"', 'with \\"quotes\\"'),
            ("back\\slash", "back\\\\slash"),
            ("line\nbreak", "line\\nbreak"),
            ("tab\there", "tab\\there"),
            ("cr\rend", "cr\\rend"),
            ("\b\f", "\\b\\f"),
            # Mixed escape + content
            ('a"b\\c\nd', 'a\\"b\\\\c\\nd'),
        ],
    )
    def test_known_escapes(self, raw: str, expected: str) -> None:
        assert escape_sparql_literal(raw) == expected

    def test_control_chars_emitted_as_unicode_escape(self) -> None:
        """C0 controls without single-char shortcut → ``\\uXXXX``."""
        # U+0001 is SOH — no single-char escape, must be hex
        assert escape_sparql_literal("\x01") == "\\u0001"
        # U+001F is unit separator — likewise
        assert escape_sparql_literal("\x1f") == "\\u001F"
        # U+0000 NUL — must not be silently dropped
        assert escape_sparql_literal("\x00") == "\\u0000"

    def test_unicode_passthrough(self) -> None:
        """Non-control Unicode passes through verbatim."""
        emoji = "ok \U0001f680 launch"
        assert escape_sparql_literal(emoji) == emoji
        cjk = "中文字符"
        assert escape_sparql_literal(cjk) == cjk

    def test_injection_attempt_cannot_break_boundary(self) -> None:
        """The classic injection payload must not produce an unescaped ``"``."""
        payload = 'foo" } INSERT DATA { <urn:evil> <urn:p> "bar'
        escaped = escape_sparql_literal(payload)
        # Wrap as it would be wrapped in real call site
        wrapped = f'"{escaped}"'
        # Every unescaped " must terminate the literal — so the wrapped
        # form should have exactly two unescaped quotes (the wrappers).
        unescaped_quotes = re.findall(r'(?<!\\)"', wrapped)
        assert len(unescaped_quotes) == 2, (
            f"injection slipped through: {wrapped!r}"
        )

    def test_double_escape_idempotency_on_safe_input(self) -> None:
        """Calling escape twice on safe input should not introduce damage."""
        safe = "F-001"
        assert escape_sparql_literal(escape_sparql_literal(safe)) == safe

    def test_typeerror_on_non_str(self) -> None:
        with pytest.raises(TypeError):
            escape_sparql_literal(123)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            escape_sparql_literal(None)  # type: ignore[arg-type]


class TestEscapeIriComponent:
    """``escape_iri_component`` — percent-encode IRI path segments."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("F-001", "F-001"),
            ("Feature", "Feature"),
            ("proj-default", "proj-default"),
            # Underscore, dot, tilde are unreserved
            ("a_b.c~d", "a_b.c~d"),
            # Path separator preserved
            ("a/b", "a/b"),
            # Spaces become %20
            ("my doc", "my%20doc"),
            # IRI-breaking chars
            ("a<b", "a%3Cb"),
            ("a>b", "a%3Eb"),
            ('a"b', "a%22b"),
            ("a{b}", "a%7Bb%7D"),
            ("a|b", "a%7Cb"),
        ],
    )
    def test_known_encodings(self, raw: str, expected: str) -> None:
        assert escape_iri_component(raw) == expected

    def test_unicode_percent_encoded(self) -> None:
        """Non-ASCII gets UTF-8 percent-encoded — strict IRIs require it
        in the form ``<...>`` even though raw IRIs allow Unicode.
        """
        result = escape_iri_component("中")
        # UTF-8 encoding of 中 is E4 B8 AD
        assert result == "%E4%B8%AD"

    def test_typeerror_on_non_str(self) -> None:
        with pytest.raises(TypeError):
            escape_iri_component(123)  # type: ignore[arg-type]


class TestAssertSafeIri:
    """``assert_safe_iri`` — boundary check on already-formed IRIs."""

    @pytest.mark.parametrize(
        "iri",
        [
            "https://cataforge.dev/instance/F-001",
            "urn:example:foo",
            "https://example.com/path?query=1&other=2",
            # %-encoded reserved chars are fine — they're already safe
            "https://example.com/my%20doc",
        ],
    )
    def test_safe_iris_pass_through(self, iri: str) -> None:
        assert assert_safe_iri(iri) == iri

    @pytest.mark.parametrize(
        "bad_iri",
        [
            "https://example.com/<inject>",
            "https://example.com/with space",
            "https://example.com/quote\"",
            "https://example.com/back\\slash",
            "https://example.com/pipe|",
            "https://example.com/brace{",
            "https://example.com/newline\nhere",
            "https://example.com/tab\there",
            "https://example.com/nul\x00",
        ],
    )
    def test_unsafe_iris_rejected(self, bad_iri: str) -> None:
        with pytest.raises(ValueError, match="forbidden character"):
            assert_safe_iri(bad_iri)

    def test_typeerror_on_non_str(self) -> None:
        with pytest.raises(TypeError):
            assert_safe_iri(123)  # type: ignore[arg-type]


class TestIntegration:
    """End-to-end: escape + wrap, escape + interpolate, check well-formedness."""

    def test_literal_wrap_produces_valid_sparql_fragment(self) -> None:
        """Wrapping the escape output in ``"..."`` yields a fragment that
        contains exactly one balanced literal — no premature close."""
        cases = [
            "simple",
            'has "quotes"',
            "back\\slash",
            "multi\nline\twith\rcontrol",
            "\x00\x01\x1f",
            "emoji \U0001f680 ok",
        ]
        for raw in cases:
            wrapped = f'"{escape_sparql_literal(raw)}"'
            # Count quotes that aren't backslash-escaped
            unescaped = re.findall(r'(?<!\\)"', wrapped)
            assert len(unescaped) == 2, (
                f"raw={raw!r} → wrapped={wrapped!r}, got {len(unescaped)} unescaped quotes"
            )

    def test_iri_angle_wrap_safe_after_encode(self) -> None:
        """``<{escape_iri_component(...)}>`` is always well-formed."""
        adversarial = [
            "F-001",
            "my doc with space",
            "evil>injected<more",
            "back\\slash",
            "中文",
        ]
        for raw in adversarial:
            encoded = escape_iri_component(raw)
            wrapped = f"<{encoded}>"
            # No interior angle brackets after encoding
            assert wrapped.count("<") == 1
            assert wrapped.count(">") == 1
            # And the encoded form must pass assert_safe_iri
            assert_safe_iri(encoded)
