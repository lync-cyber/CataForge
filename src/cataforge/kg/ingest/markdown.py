"""Top-level markdown → KG triples entry point.

Composes :mod:`.frontmatter`, :mod:`.prose_refs`, and :mod:`.canonical` into
a single ``ingest_markdown`` call. The output is a list of
:class:`~cataforge.kg.store.Triple` ready to hand to ``GraphStore.add``.

IRI scheme (design §1.8 rule 2):

* Document → ``cfk:doc/<doc_id>``
* Item     → ``cfa:<doc_id>/<display_id>``

ID-prefix → concrete artifact class lookup lives in :data:`ID_PREFIX_MAP`;
the table is authoritative for the ingest path. SHACL shapes (validated
later, not here) enforce the matching per-class ID regex.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from cataforge.kg.ingest.canonical import canonicalize
from cataforge.kg.ingest.frontmatter import frontmatter_to_triples
from cataforge.kg.ingest.prose_refs import scan_prose_refs
from cataforge.kg.store import Triple
from cataforge.utils.frontmatter import split_yaml_frontmatter
from cataforge.utils.md_parse import iter_markdown_headings

ID_PREFIX_MAP: dict[str, str] = {
    "F":   "cfa:Feature",
    "US":  "cfa:UserStory",
    "NFR": "cfa:NFR",
    "M":   "cfa:Module",
    "C":   "cfa:Component",
    "I":   "cfa:Interface",
    "WF":  "cfa:Workflow",
    "CU":  "cfa:CodeUnit",
    "TC":  "cfa:TestCase",
    "TS":  "cfa:TestSuite",
    "AC":  "cfa:AcceptanceCriterion",
    "T":   "cfa:Task",
    "D":   "cfa:Decision",
    "R":   "cfa:Risk",
    "INC": "cfa:Incident",
}

_DISPLAY_ID_PREFIX_RE = re.compile(r"^([A-Z]+)-\d+")
_HEADING_ID_RE = re.compile(r"^([A-Z]+-\d+)(?:\s+(.*))?$")
_SEMVER_ID_RE = re.compile(r"^(v\d+\.\d+\.\d+)(?:\s+(.*))?$")


@dataclass(frozen=True)
class DocumentNode:
    """Parsed document-level metadata kept around for IRI/label resolution."""

    iri: str
    doc_id: str
    file_path: str
    content_hash: str
    label: str | None
    doc_type: str | None


@dataclass(frozen=True)
class ItemNode:
    """An ID-headed section within a document — the units that participate
    in V-model traceability."""

    iri: str
    display_id: str
    item_class: str
    label: str
    document_iri: str


@dataclass(frozen=True)
class IngestResult:
    """Public return value: triples plus the structural nodes the caller
    needs to resolve cross-document references later."""

    triples: list[Triple]
    document: DocumentNode | None
    items: list[ItemNode] = field(default_factory=list)


def _content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]


def _classify_display_id(display_id: str) -> str | None:
    """Map ``F-001`` / ``v0.5.0`` / etc. to its concrete cfa class."""
    if _SEMVER_ID_RE.match(display_id):
        return "cfa:Release"
    m = _DISPLAY_ID_PREFIX_RE.match(display_id)
    if not m:
        return None
    return ID_PREFIX_MAP.get(m.group(1))


def _strip_section_number(title: str) -> str:
    """Drop a leading ``2.3`` / ``2.3.4`` / ``2.`` numbering token."""
    return re.sub(r"^\d+(\.\d+)*\.?\s+", "", title).strip()


def _split_heading_id(title: str) -> tuple[str | None, str]:
    """Try ``<display_id> <label>`` first, then ``vX.Y.Z <label>``.

    Returns (display_id, label_text). ``display_id`` is None when the
    heading is plain prose (no ID at the start)."""
    cleaned = _strip_section_number(title)
    m = _HEADING_ID_RE.match(cleaned)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    m = _SEMVER_ID_RE.match(cleaned)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    return None, cleaned


def _doc_iri(doc_id: str) -> str:
    return f"cfk:doc/{doc_id}"


def _item_iri(doc_id: str, display_id: str) -> str:
    return f"cfa:{doc_id}/{display_id}"


def _emit_document_triples(doc: DocumentNode) -> list[Triple]:
    out: list[Triple] = [
        Triple(s=doc.iri, p="rdf:type", o="cfk:Document"),
        Triple(s=doc.iri, p="cfk:hasId", o=doc.doc_id),
        Triple(s=doc.iri, p="cfk:contentHash", o=doc.content_hash),
        Triple(s=doc.iri, p="cfk:source", o=doc.file_path),
    ]
    if doc.label:
        out.append(Triple(s=doc.iri, p="rdfs:label", o=doc.label))
    if doc.doc_type:
        out.append(Triple(s=doc.iri, p="dct:type", o=doc.doc_type))
    return out


def _emit_item_triples(item: ItemNode) -> list[Triple]:
    return [
        Triple(s=item.iri, p="rdf:type", o=item.item_class),
        Triple(s=item.iri, p="cfk:hasId", o=item.display_id),
        Triple(s=item.iri, p="rdfs:label", o=item.label or item.display_id),
        Triple(s=item.iri, p="cfk:definedIn", o=item.document_iri),
    ]


def _build_items(
    headings: list[tuple[int, int, str]],
    doc_id: str,
    doc_iri: str,
) -> list[ItemNode]:
    items: list[ItemNode] = []
    seen_ids: set[str] = set()
    for _line, level, title in headings:
        if level < 2:
            continue
        display_id, label = _split_heading_id(title)
        if display_id is None or display_id in seen_ids:
            continue
        item_class = _classify_display_id(display_id)
        if item_class is None:
            continue
        seen_ids.add(display_id)
        items.append(
            ItemNode(
                iri=_item_iri(doc_id, display_id),
                display_id=display_id,
                item_class=item_class,
                label=label,
                document_iri=doc_iri,
            ),
        )
    return items


def ingest_markdown(
    file_path: Path,
    *,
    project_root: Path | None = None,
    known_item_iris: dict[str, str] | None = None,
) -> IngestResult:
    """Parse a single Markdown file and return its triples plus structure.

    Documents lacking a ``id`` frontmatter field are returned with
    ``document=None`` and an empty triple list — the caller decides whether
    to warn (the migrator emits an orphan report mirroring
    :func:`cataforge.docs.indexer.find_orphan_docs`)."""
    raw = file_path.read_text(encoding="utf-8")
    fm, body = split_yaml_frontmatter(raw)
    fm = fm or {}

    doc_id = str(fm.get("id", "")).strip()
    if not doc_id or "{" in doc_id:
        return IngestResult(triples=[], document=None, items=[])

    rel_path: str
    if project_root is not None:
        try:
            rel_path = str(file_path.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel_path = str(file_path)
    else:
        rel_path = str(file_path)
    rel_path = rel_path.replace("\\", "/")

    headings = iter_markdown_headings(raw)
    # Document title falls back to the first h1 if frontmatter omits ``label``.
    first_h1 = next((title for _, lvl, title in headings if lvl == 1), None)
    label = str(fm.get("label", "")).strip() or first_h1 or doc_id

    document = DocumentNode(
        iri=_doc_iri(doc_id),
        doc_id=doc_id,
        file_path=rel_path,
        content_hash=_content_hash(body),
        label=label,
        doc_type=str(fm.get("doc_type", "")).strip() or None,
    )

    items = _build_items(headings, doc_id=doc_id, doc_iri=document.iri)

    triples: list[Triple] = []
    triples.extend(_emit_document_triples(document))
    triples.extend(
        frontmatter_to_triples(
            document.iri, fm,
            own_item_iris={it.display_id: it.iri for it in items},
            known_item_iris=known_item_iris,
        ),
    )
    for item in items:
        triples.extend(_emit_item_triples(item))

    own_iri_map = {it.display_id: it.iri for it in items}
    triples.extend(
        scan_prose_refs(
            body, source_iri=document.iri, known_item_iris=own_iri_map,
        ),
    )

    return IngestResult(
        triples=canonicalize(triples),
        document=document,
        items=items,
    )
