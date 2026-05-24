"""Render-twice idempotency checker."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cataforge.kg.render.checker import (
    IdempotencyCheckResult,
    check_render_idempotent,
)
from cataforge.kg.render.engine import KGRenderer
from cataforge.kg.store import RDFLibStore, Triple


@pytest.fixture
def store_and_tpl(tmp_path: Path):
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-001", "cfk:hasId", "F-001"),
    ])
    tpl = tmp_path / "tpl"
    tpl.mkdir()
    return store, tpl


def test_idempotent_template_passes(store_and_tpl) -> None:
    store, tpl = store_and_tpl
    (tpl / "ok.md.j2").write_text(textwrap.dedent("""\
        # Features
        {% for r in kg.query('SELECT ?id WHERE { ?x cfk:hasId ?id } ORDER BY ?id') %}
        - {{ r.id }}
        {% endfor %}
    """), encoding="utf-8")
    r = KGRenderer(store, template_roots=[tpl])
    result = check_render_idempotent(r, "ok.md.j2")
    assert result.is_idempotent
    assert result.diff_preview == ""


def test_two_real_renders_compared_byte_for_byte(store_and_tpl) -> None:
    """A non-trivial template with SPARQL + filters must remain idempotent
    across repeated invocation — this is the regression guard for R-03."""
    store, tpl = store_and_tpl
    store.add([
        Triple("cfa:prd/F-002", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-002", "cfk:hasId", "F-002"),
        Triple("cfa:arch/M-001", "rdf:type", "cfa:Module"),
        Triple("cfa:arch/M-001", "cfk:hasId", "M-001"),
    ])
    (tpl / "rich.md.j2").write_text(textwrap.dedent("""\
        # Snapshot
        {{ kg.query('SELECT ?id WHERE { ?x cfk:hasId ?id } ORDER BY ?id') | table(columns=['id']) }}
    """), encoding="utf-8")
    r = KGRenderer(store, template_roots=[tpl])
    result = check_render_idempotent(r, "rich.md.j2")
    assert result.is_idempotent, result.diff_preview


def test_diff_preview_reports_first_diverging_line() -> None:
    result = IdempotencyCheckResult(
        template_name="t",
        is_idempotent=False,
        first="line1\nline2-a\nline3",
        second="line1\nline2-b\nline3",
    )
    assert "line 2" in result.diff_preview
    assert "line2-a" in result.diff_preview
    assert "line2-b" in result.diff_preview


def test_diff_preview_reports_length_mismatch_when_common_prefix_matches() -> None:
    result = IdempotencyCheckResult(
        template_name="t", is_idempotent=False,
        first="a\nb", second="a\nb\nextra",
    )
    assert "length differs" in result.diff_preview


def test_diff_preview_empty_when_identical() -> None:
    result = IdempotencyCheckResult(
        template_name="t", is_idempotent=True,
        first="same", second="same",
    )
    assert result.diff_preview == ""
