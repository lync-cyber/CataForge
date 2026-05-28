"""Tests for doctor kg_ingestion false-positive fixes (A7)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class _FakePaths:
    root: Path

    @property
    def framework_json(self) -> Path:
        return self.root / ".cataforge" / "framework.json"


@dataclass
class _FakeCfg:
    paths: _FakePaths


class TestFencedCodeBlockFalsePositive:
    def test_http_like_id_in_fenced_block_not_extracted(self) -> None:
        """HTTP-100 inside a fenced code block must not be treated as an entity ID."""
        from cataforge.cli.doctor.kg_ingestion import _scan_markdown_entity_ids

        content = "Some text\n```\nHTTP-100 response code\nERR-404 not found\n```\n"
        ids = _scan_markdown_entity_ids(content)
        assert "HTTP-100" not in ids
        assert "ERR-404" not in ids

    def test_non_whitelisted_prefix_not_extracted(self) -> None:
        """ERR-404 uses a prefix not in ENTITY_PREFIX_TO_CLASS — must be ignored."""
        from cataforge.cli.doctor.kg_ingestion import _scan_markdown_entity_ids

        content = "The server returned ERR-404 and HTTP-200 status codes.\n"
        ids = _scan_markdown_entity_ids(content)
        assert "ERR-404" not in ids
        assert "HTTP-200" not in ids

    def test_inline_code_not_extracted(self) -> None:
        """Entity-like strings inside inline code must be skipped."""
        from cataforge.cli.doctor.kg_ingestion import _scan_markdown_entity_ids

        content = "See `F-001` for details — but `HTTP-100` is not an entity.\n"
        ids = _scan_markdown_entity_ids(content)
        assert "F-001" not in ids
        assert "HTTP-100" not in ids

    def test_whitelisted_id_outside_code_block_is_extracted(self) -> None:
        """F-001 in plain text must still be found."""
        from cataforge.cli.doctor.kg_ingestion import _scan_markdown_entity_ids

        content = "### Feature F-001 Login\n\nThis feature enables login.\n"
        ids = _scan_markdown_entity_ids(content)
        assert "F-001" in ids


class TestFrontmatterPriority:
    def test_frontmatter_id_used_when_present(self) -> None:
        """When frontmatter has id: F-001, only that ID is collected (not regex scan)."""
        from cataforge.cli.doctor.kg_ingestion import (
            _extract_frontmatter_id,
        )

        content = "---\nid: F-001\ndoc_type: prd\n---\n\nSome body text.\n"
        fm_id = _extract_frontmatter_id(content)
        assert fm_id == "F-001"

    def test_frontmatter_id_not_found_falls_back_to_regex(self) -> None:
        """Without frontmatter id, regex scan is used and finds whitelisted IDs."""
        from cataforge.cli.doctor.kg_ingestion import (
            _extract_frontmatter_id,
            _scan_markdown_entity_ids,
        )

        content = "---\ndoc_type: prd\n---\n\n### §2 Feature F-002\n"
        fm_id = _extract_frontmatter_id(content)
        assert fm_id is None

        ids = _scan_markdown_entity_ids(content)
        assert "F-002" in ids

    def test_no_frontmatter_falls_back_to_regex(self) -> None:
        from cataforge.cli.doctor.kg_ingestion import (
            _extract_frontmatter_id,
            _scan_markdown_entity_ids,
        )

        content = "# A document\n\nM-001 is a module.\n"
        fm_id = _extract_frontmatter_id(content)
        assert fm_id is None

        ids = _scan_markdown_entity_ids(content)
        assert "M-001" in ids

    def test_scan_fs_uses_frontmatter_id_over_body_scan(self, tmp_path: Path) -> None:
        """_scan_fs_entity_ids picks frontmatter id and does not add body IDs."""
        from cataforge.cli.doctor.kg_ingestion import _scan_fs_entity_ids

        docs_prd = tmp_path / "docs" / "prd"
        docs_prd.mkdir(parents=True)
        (docs_prd / "test.md").write_text(
            "---\nid: F-001\n---\n\nMentions F-002 in body.\n",
            encoding="utf-8",
        )

        ids = _scan_fs_entity_ids(tmp_path, {"prd"}, {"prd": "prd"})
        assert "F-001" in ids
        assert "F-002" not in ids
