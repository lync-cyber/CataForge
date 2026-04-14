"""Front matter + markdown-it heading extraction."""

from __future__ import annotations

from cataforge.schema.framework import FrameworkFile
from cataforge.utils.frontmatter import split_yaml_frontmatter
from cataforge.utils.md_parse import iter_markdown_headings


def test_split_frontmatter_roundtrip() -> None:
    raw = "---\nid: x\n---\n\n# Hello\n"
    meta, body = split_yaml_frontmatter(raw)
    assert meta is not None
    assert meta.get("id") == "x"
    assert "# Hello" in body


def test_no_frontmatter() -> None:
    meta, body = split_yaml_frontmatter("# Only")
    assert meta is None
    assert body == "# Only"


def test_iter_markdown_headings() -> None:
    md = "# A\n\n## B\n\nPara.\n"
    h = iter_markdown_headings(md)
    assert len(h) >= 2
    assert h[0][2].strip() == "A"
    assert h[1][2].strip() == "B"


def test_framework_file_validate() -> None:
    fw = FrameworkFile.model_validate(
        {"version": "0.4", "runtime": {"platform": "cursor"}}
    )
    assert fw.version == "0.4"
    assert fw.runtime is not None
    assert fw.runtime.platform == "cursor"
