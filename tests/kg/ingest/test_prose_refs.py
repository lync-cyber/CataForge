"""Prose ID-reference scanner — must skip code, must resolve known IDs."""

from __future__ import annotations

from cataforge.kg.ingest.prose_refs import scan_prose_refs


def _ids(triples) -> set[tuple[str, str]]:
    return {(t.p, t.o) for t in triples}


def test_resolves_known_id_in_prose() -> None:
    body = "实现见 F-001 一节。"
    known = {"F-001": "cfa:prd-x/F-001"}
    out = list(scan_prose_refs(body, "cfk:doc/prd-x", known))
    assert _ids(out) == {("cfa:references", "cfa:prd-x/F-001")}


def test_ignores_id_inside_inline_code() -> None:
    body = "调用 `F-001` 函数即可。"
    known = {"F-001": "cfa:prd-x/F-001"}
    assert list(scan_prose_refs(body, "cfk:doc/prd-x", known)) == []


def test_ignores_id_inside_fenced_code_block() -> None:
    body = "示例：\n\n```\nseed = F-001\n```\n"
    known = {"F-001": "cfa:prd-x/F-001"}
    assert list(scan_prose_refs(body, "cfk:doc/prd-x", known)) == []


def test_unknown_id_dropped() -> None:
    body = "也请 cross-check F-999."
    known = {"F-001": "cfa:prd-x/F-001"}
    assert list(scan_prose_refs(body, "cfk:doc/prd-x", known)) == []


def test_self_reference_dropped() -> None:
    body = "F-001 自引用不算"
    known = {"F-001": "cfa:prd-x/F-001"}
    out = list(scan_prose_refs(body, "cfa:prd-x/F-001", known))
    assert out == []


def test_multiple_ids_deduplicated() -> None:
    body = "Both F-001 and F-002. F-001 again."
    known = {
        "F-001": "cfa:prd-x/F-001",
        "F-002": "cfa:prd-x/F-002",
    }
    out = list(scan_prose_refs(body, "cfk:doc/prd-x", known))
    assert _ids(out) == {
        ("cfa:references", "cfa:prd-x/F-001"),
        ("cfa:references", "cfa:prd-x/F-002"),
    }
