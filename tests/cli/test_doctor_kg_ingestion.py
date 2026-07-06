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
        from cataforge.domain.kg.ingest.entity_extract import _DEFAULT_REGISTRY
        from cataforge.interface.cli.doctor.kg_ingestion import _scan_markdown_entity_ids

        content = "Some text\n```\nHTTP-100 response code\nERR-404 not found\n```\n"
        ids = _scan_markdown_entity_ids(content, _DEFAULT_REGISTRY.entity_re)
        assert "HTTP-100" not in ids
        assert "ERR-404" not in ids

    def test_non_whitelisted_prefix_not_extracted(self) -> None:
        """ERR-404 uses a prefix not in ENTITY_PREFIX_TO_CLASS — must be ignored."""
        from cataforge.domain.kg.ingest.entity_extract import _DEFAULT_REGISTRY
        from cataforge.interface.cli.doctor.kg_ingestion import _scan_markdown_entity_ids

        content = "The server returned ERR-404 and HTTP-200 status codes.\n"
        ids = _scan_markdown_entity_ids(content, _DEFAULT_REGISTRY.entity_re)
        assert "ERR-404" not in ids
        assert "HTTP-200" not in ids

    def test_inline_code_not_extracted(self) -> None:
        """Entity-like strings inside inline code must be skipped."""
        from cataforge.domain.kg.ingest.entity_extract import _DEFAULT_REGISTRY
        from cataforge.interface.cli.doctor.kg_ingestion import _scan_markdown_entity_ids

        content = "See `F-001` for details — but `HTTP-100` is not an entity.\n"
        ids = _scan_markdown_entity_ids(content, _DEFAULT_REGISTRY.entity_re)
        assert "F-001" not in ids
        assert "HTTP-100" not in ids

    def test_whitelisted_id_outside_code_block_is_extracted(self) -> None:
        """F-001 in plain text must still be found."""
        from cataforge.domain.kg.ingest.entity_extract import _DEFAULT_REGISTRY
        from cataforge.interface.cli.doctor.kg_ingestion import _scan_markdown_entity_ids

        content = "### Feature F-001 Login\n\nThis feature enables login.\n"
        ids = _scan_markdown_entity_ids(content, _DEFAULT_REGISTRY.entity_re)
        assert "F-001" in ids


class TestScanCollectsItemIds:
    """``_scan_fs_entity_ids`` collects item-level ids (F-/M-/...), the only
    ids the importer mints as ``cf:entity_id``. A document-level frontmatter
    ``id`` is not an entity and must not be treated as a required one."""

    def test_item_ids_collected_regardless_of_doc_level_frontmatter_id(
        self, tmp_path: Path
    ) -> None:
        from cataforge.domain.kg.ingest.entity_extract import _DEFAULT_REGISTRY
        from cataforge.interface.cli.doctor.kg_ingestion import _scan_fs_entity_ids

        docs_prd = tmp_path / "docs" / "prd"
        docs_prd.mkdir(parents=True)
        (docs_prd / "test.md").write_text(
            "---\nid: prd-myapp\n---\n\n### F-001 Login\n\nDepends on M-001.\n",
            encoding="utf-8",
        )

        ids = _scan_fs_entity_ids(tmp_path, {"prd"}, {"prd": "prd"}, _DEFAULT_REGISTRY.entity_re)
        assert ids == {"F-001", "M-001"}
        # The doc-level frontmatter id is not a cf:entity_id; it must not be
        # demanded of the graph (the importer never mints it).
        assert "prd-myapp" not in ids
