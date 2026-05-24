"""Jinja2 filters — bullet_list / table / mermaid_diagram / link_to."""

from __future__ import annotations

from cataforge.kg.render.filters import (
    bullet_list,
    link_to,
    mermaid_diagram,
    table,
)


def test_bullet_list_basic() -> None:
    rows = [{"label": "first"}, {"label": "second"}]
    assert bullet_list(rows) == "- first\n- second"


def test_bullet_list_custom_format() -> None:
    rows = [{"id": "F-001", "label": "login"}]
    assert bullet_list(rows, fmt="{id}: {label}") == "- F-001: login"


def test_bullet_list_missing_key_skipped() -> None:
    rows = [{"label": "ok"}, {"other": "missing"}]
    assert bullet_list(rows) == "- ok"


def test_bullet_list_empty_input_empty_output() -> None:
    assert bullet_list([]) == ""


def test_table_with_auto_columns() -> None:
    rows = [{"id": "F-001", "label": "login"}]
    out = table(rows)
    assert "| id | label |" in out
    assert "| --- | --- |" in out
    assert "| F-001 | login |" in out


def test_table_explicit_columns_order() -> None:
    rows = [{"id": "F-001", "label": "login"}]
    out = table(rows, columns=["label", "id"])
    assert "| label | id |" in out


def test_table_empty_rows_returns_empty_string() -> None:
    assert table([]) == ""


def test_table_missing_cells_render_empty() -> None:
    rows = [{"id": "F-001"}, {"label": "signup"}]
    out = table(rows, columns=["id", "label"])
    # Whitespace canonicalisation collapses the double-space around empty
    # cells to a single space — still valid markdown.
    assert "| F-001 | |" in out
    assert "| | signup |" in out


def test_mermaid_diagram_basic_edges() -> None:
    edges = [
        {"src": "A", "dst": "B"},
        {"src": "B", "dst": "C"},
    ]
    out = mermaid_diagram(edges)
    assert out.startswith("graph LR")
    assert "A --> B" in out
    assert "B --> C" in out


def test_mermaid_diagram_sorts_edges_deterministically() -> None:
    edges_a = [{"src": "B", "dst": "C"}, {"src": "A", "dst": "B"}]
    edges_b = [{"src": "A", "dst": "B"}, {"src": "B", "dst": "C"}]
    assert mermaid_diagram(edges_a) == mermaid_diagram(edges_b)


def test_mermaid_diagram_sanitises_node_ids() -> None:
    # CURIE colons and slashes are not legal mermaid node IDs.
    edges = [{"src": "cfa:prd/F-001", "dst": "cfa:arch/M-001"}]
    out = mermaid_diagram(edges)
    assert "cfa_prd_F_001" in out
    assert ":" not in out.split("\n", 1)[1]


def test_mermaid_diagram_empty_returns_header_only() -> None:
    assert mermaid_diagram([]) == "graph LR"


def test_mermaid_diagram_with_label() -> None:
    edges = [{"src": "A", "dst": "B", "via": "implements"}]
    out = mermaid_diagram(edges, label_key="via")
    assert "-- implements -->" in out


def test_link_to_doc_slug_local_id() -> None:
    out = link_to("cfa:prd-x/F-001")
    assert out == "[F-001](docs/prd-x.md#F-001)"


def test_link_to_with_explicit_label() -> None:
    out = link_to("cfa:prd-x/F-001", label="用户登录")
    assert "用户登录" in out
    assert "docs/prd-x.md#F-001" in out


def test_link_to_bare_iri_falls_back() -> None:
    out = link_to("cfk:Resource")
    assert out == "cfk:Resource"
