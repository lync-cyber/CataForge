"""Tests for cataforge.utils.frontmatter — YAML front matter splitting."""

from __future__ import annotations

from cataforge.utils.frontmatter import split_yaml_frontmatter


class TestSplitYamlFrontmatter:
    def test_valid_frontmatter(self) -> None:
        raw = "---\ntitle: Hello\n---\nBody text.\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta == {"title": "Hello"}
        assert body == "Body text.\n"

    def test_no_frontmatter(self) -> None:
        raw = "# Just a heading\nSome text.\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta is None
        assert body == raw

    def test_missing_closing_fence_returns_none(self) -> None:
        raw = "---\ntitle: No close\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta is None
        assert body == raw

    def test_midline_dashes_not_treated_as_fence(self) -> None:
        raw = "---\ntitle: Test\n---\nSome ---horizontal--- dashes here.\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta == {"title": "Test"}
        assert "---horizontal---" in body

    def test_inline_dashes_in_frontmatter_body_not_fence(self) -> None:
        raw = "---\ntitle: Test\nsome_key: a---b\n---\nBody.\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta is not None
        assert body == "Body.\n"

    def test_horizontal_rule_in_content_not_closing_fence(self) -> None:
        raw = "---\ntitle: Doc\n---\nParagraph.\n\n---\n\nAnother section.\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta == {"title": "Doc"}
        assert "---" in body

    def test_empty_frontmatter_returns_empty_dict(self) -> None:
        raw = "---\n---\nBody.\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta == {}
        assert body == "Body.\n"

    def test_malformed_yaml_returns_empty_dict(self) -> None:
        raw = "---\n: invalid: yaml: {{\n---\nBody.\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta == {}
        assert body == "Body.\n"

    def test_non_dict_yaml_returns_empty_dict(self) -> None:
        raw = "---\n- item1\n- item2\n---\nBody.\n"
        meta, body = split_yaml_frontmatter(raw)
        assert meta == {}

    def test_body_strip_leading_newline(self) -> None:
        raw = "---\ntitle: T\n---\nContent.\n"
        _, body = split_yaml_frontmatter(raw)
        assert body == "Content.\n"
