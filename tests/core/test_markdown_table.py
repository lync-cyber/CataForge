"""Unit tests for the shared GFM pipe-table parser."""

from __future__ import annotations

from cataforge.core.markdown_sections import parse_markdown_table

_SIX_COL = """\
### 1.4 技术栈
| 层次 | 技术 | 版本 | 生命周期 | 选型理由 | 调研来源 |
|------|------|------|----------|----------|----------|
| 后端 | Python 3.12 | 3.12 | Stable | 类型系统成熟 | tech-eval |
| 认证 | JWT | 2.x | Stable | 无状态标准 | - |

## 2. 其他
"""


def test_parses_headers_and_rows() -> None:
    table = parse_markdown_table(_SIX_COL)
    assert table is not None
    assert table.headers == ["层次", "技术", "版本", "生命周期", "选型理由", "调研来源"]
    assert len(table.rows) == 2
    assert table.rows[0] == ["后端", "Python 3.12", "3.12", "Stable", "类型系统成熟", "tech-eval"]


def test_stops_at_blank_line_after_data() -> None:
    """Rows following the table (## 2. 其他) are not swallowed."""
    table = parse_markdown_table(_SIX_COL)
    assert table is not None
    assert len(table.rows) == 2


def test_leading_and_trailing_pipes_optional() -> None:
    table = parse_markdown_table("a | b\n--- | ---\n1 | 2\n")
    assert table is not None
    assert table.headers == ["a", "b"]
    assert table.rows == [["1", "2"]]


def test_no_table_returns_none() -> None:
    assert parse_markdown_table("- 后端: Python 3.12\n- 认证: JWT\n") is None
    assert parse_markdown_table("just prose, no pipes\n") is None


def test_short_row_not_padded() -> None:
    """A row with fewer cells than the header is returned verbatim."""
    table = parse_markdown_table("| a | b | c |\n|---|---|---|\n| 1 | 2 |\n")
    assert table is not None
    assert table.rows == [["1", "2"]]


def test_empty_cells_preserved() -> None:
    table = parse_markdown_table("| a | b |\n|---|---|\n| 1 |  |\n")
    assert table is not None
    assert table.rows == [["1", ""]]
