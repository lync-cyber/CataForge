"""Design §4.3 stability invariant: render(d) → write → ingest → render(d)
must produce the same output as the first render.

This is stronger than render-twice idempotency (which only fixes the
store state). The render-write-ingest-render round-trip is the path the
PostToolUse auto-ingest hook walks every time a user edits a rendered
file; if it isn't a no-op, every edit produces phantom triples and the
3-way merge accumulates conflicts. Risk R-03 in the design register."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from cataforge.kg.delta import apply as delta_apply
from cataforge.kg.delta import compute_delta
from cataforge.kg.ingest.markdown import ingest_markdown
from cataforge.kg.render.engine import KGRenderer
from cataforge.kg.store import RDFLibStore, Triple

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = REPO_ROOT / ".cataforge" / "skills" / "doc-gen" / "templates" / "standard"


@pytest.fixture
def store_for_prd(tmp_path: Path) -> Iterator[RDFLibStore]:
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfk:doc/prd-acme", "rdf:type", "cfk:Document"),
        Triple("cfk:doc/prd-acme", "cfk:hasId", "prd-acme"),
        Triple("cfk:doc/prd-acme", "rdfs:label", "ACME PRD"),
        Triple("cfa:prd-acme/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd-acme/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:prd-acme/F-001", "rdfs:label", "login"),
        Triple("cfa:prd-acme/F-001", "cfk:definedIn", "cfk:doc/prd-acme"),
    ])
    store.persist()
    yield store


def test_render_after_noop_ingest_unchanged(
    store_for_prd: RDFLibStore, tmp_path: Path,
) -> None:
    renderer = KGRenderer(store_for_prd, template_roots=[TEMPLATE_DIR])
    first = renderer.render(
        "prd.md.j2", doc="cfk:doc/prd-acme", project="prd-acme",
    )

    rendered_path = tmp_path / "docs" / "prd-acme.md"
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text(first, encoding="utf-8")

    # Re-ingest the rendered file back into the KG. The ingest result's
    # triple set must be a subset of (or compatible with) what's already
    # in the store — i.e. nothing genuinely new gets added.
    result = ingest_markdown(rendered_path, project_root=tmp_path)
    assert result.document is not None
    scope = {result.document.iri} | {it.iri for it in result.items}

    kg_triples = [
        _shorten_triple(s, p, o) for s, p, o, _ in store_for_prd
    ]
    delta = compute_delta(
        kg_triples, result.triples, subject_scope=scope,
    )
    delta_apply(delta, store_for_prd, strategy="kg-wins")

    second = renderer.render(
        "prd.md.j2", doc="cfk:doc/prd-acme", project="prd-acme",
    )
    assert first == second, (
        "render → write → ingest → render must be a no-op (R-03). "
        "Conflict count: "
        f"{len(delta.conflicts)}; additions: {len(delta.additions)}; "
        f"removals: {len(delta.removals)}"
    )


_PREFIX_MAP = {
    "https://cataforge.dev/ontology/kernel#":   "cfk:",
    "https://cataforge.dev/ontology/process#":  "cfp:",
    "https://cataforge.dev/ontology/artifact#": "cfa:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://www.w3.org/2000/01/rdf-schema#":       "rdfs:",
    "http://purl.org/dc/terms/":                   "dct:",
}


def _shorten(iri: str) -> str:
    for prefix, short in _PREFIX_MAP.items():
        if iri.startswith(prefix):
            return short + iri[len(prefix):]
    return iri


def _shorten_triple(s: str, p: str, o: str) -> Triple:
    return Triple(s=_shorten(s), p=_shorten(p), o=_shorten(o))
