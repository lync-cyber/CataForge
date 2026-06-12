"""Whole-document KG → Markdown reconstruction.

`compile_documents()` rebuilds each source Markdown file from its
`cf:Document` node by concatenating the verbatim frontmatter block, the
preamble (H1 line and lead prose), and every owned `cf:Section`'s
`narrative_body` in document order (`cf:position`). The result is
doc_type-independent — no Jinja version template is applied; the graph
already holds the source slices.

Business entities that no Document covers (authored directly into the
graph with a `cf:source_doc` that has no Document node) fall back to the
per-entity card export so they still surface on disk.

Idempotency: every section slice and the preamble are stored with
trailing blank lines trimmed, joined by a fixed `"\\n\\n"`, and the file
ends in a single newline — so two runs over an unchanged store produce
the same bytes for every file.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.export.pipeline import compile_to_markdown
from cataforge.domain.kg.export.types import CompileResult, FileExportRecord

if TYPE_CHECKING:
    import pyoxigraph as ox

logger = logging.getLogger(__name__)

_SECTION_JOINER = "\n\n"


def _list_documents(store: ox.Store, namespace: str) -> list[dict[str, str]]:
    """Return one record per `cf:Document` node carrying a `cf:source_path`.

    A Document without a `source_path` was not derived from a scanned file
    (it cannot be written back), so it is skipped here.
    """
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?doc ?source_path ?doc_type ?frontmatter ?preamble WHERE { "
        "  ?doc a cf:Document ; cf:source_path ?source_path . "
        "  OPTIONAL { ?doc cf:doc_type ?doc_type } "
        "  OPTIONAL { ?doc cf:frontmatter_raw ?frontmatter } "
        "  OPTIONAL { ?doc cf:preamble_body ?preamble } "
        "} ORDER BY ?source_path"
    )
    out: list[dict[str, str]] = []
    for row in select_rows(store, sparql):
        doc_iri = _strv(_row_lookup(row, "doc"))
        source_path = _strv(_row_lookup(row, "source_path"))
        if doc_iri is None or source_path is None:
            continue
        out.append(
            {
                "doc_iri": doc_iri,
                "source_path": source_path,
                "doc_type": _strv(_row_lookup(row, "doc_type")) or "",
                "frontmatter_raw": _strv(_row_lookup(row, "frontmatter")) or "",
                "preamble_body": _strv(_row_lookup(row, "preamble")) or "",
            }
        )
    return out


def _section_bodies(store: ox.Store, namespace: str, doc_iri: str) -> list[str]:
    """Return a Document's level-2 section bodies in document order.

    Only level-2 sections are concatenated: each level-2 `narrative_body`
    already contains its nested subsections verbatim, so they tile-cover
    the document body without overlap. Deeper sections exist for
    section-level reads but would double-count here.
    """
    safe = escape_sparql_literal(doc_iri)
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?body ?position WHERE { "
        f"  ?s a cf:Section ; cf:part_of_document <{safe}> ; "
        "     cf:narrative_body ?body ; "
        '     cf:section_level "2" . '
        "  OPTIONAL { ?s cf:position ?position } "
        "} ORDER BY ?position"
    )
    out: list[str] = []
    for row in select_rows(store, sparql):
        body = _strv(_row_lookup(row, "body"))
        if body is not None:
            out.append(body)
    return out


def _assemble(frontmatter_raw: str, preamble_body: str, section_bodies: list[str]) -> str:
    """Concatenate frontmatter + preamble + sections into canonical Markdown.

    Preamble and section slices arrive with trailing blanks trimmed;
    sections join on a single blank line and the file ends with one
    newline. `frontmatter_raw` already carries its closing-fence newline.
    """
    blocks = [b for b in (preamble_body, *section_bodies) if b]
    content = _SECTION_JOINER.join(blocks)
    return f"{frontmatter_raw}{content}\n" if content else frontmatter_raw


def _covered_source_docs(store: ox.Store, namespace: str) -> set[str]:
    """Return `cf:source_doc` values that a Document node accounts for.

    An entity whose `cf:source_doc` is in this set is reconstructed inside
    a whole-document file; everything else is an orphan needing a card.
    """
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT DISTINCT ?source_doc WHERE { ?doc a cf:Document ; cf:source_doc ?source_doc }"
    )
    out: set[str] = set()
    for row in select_rows(store, sparql):
        src = _strv(_row_lookup(row, "source_doc"))
        if src is not None:
            out.add(src)
    return out


def _orphan_entity_ids(store: ox.Store, namespace: str, covered: set[str]) -> set[str]:
    """Return entity_ids whose `cf:source_doc` is not covered by any Document."""
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?entity_id ?source_doc WHERE { "
        "  ?s a ?cls ; cf:entity_id ?entity_id . "
        "  OPTIONAL { ?s cf:source_doc ?source_doc } "
        "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        "  FILTER(?cls != cf:Project) "
        "}"
    )
    out: set[str] = set()
    for row in select_rows(store, sparql):
        eid = _strv(_row_lookup(row, "entity_id"))
        if eid is None:
            continue
        src = _strv(_row_lookup(row, "source_doc"))
        if src is None or src not in covered:
            out.add(eid)
    return out


def _relative_output(source_path: str) -> Path:
    """Map a project-root-relative `source_path` to its `output_dir`-relative form.

    `output_dir` is the docs root, so the leading `docs/` segment is
    dropped: `docs/prd/prd.md` → `prd/prd.md`.
    """
    parts = Path(source_path).as_posix().split("/")
    if parts and parts[0] == "docs":
        parts = parts[1:]
    return Path(*parts) if parts else Path(source_path)


def compile_documents(
    store: ox.Store,
    output_dir: Path,
    *,
    namespace: str = "https://cataforge.dev/ontology/",
) -> CompileResult:
    """Reconstruct every source Markdown file from the graph.

    Files land at ``output_dir/<source_path without leading "docs/">``.
    Business entities not covered by any Document fall back to per-entity
    cards via :func:`compile_to_markdown` restricted to the orphan subset.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    namespace = namespace.rstrip("/") + "/"

    file_records: list[FileExportRecord] = []
    errors: list[tuple[str, str]] = []

    documents = _list_documents(store, namespace)
    for doc in documents:
        try:
            sections = _section_bodies(store, namespace, doc["doc_iri"])
            content = _assemble(doc["frontmatter_raw"], doc["preamble_body"], sections)
            out_file = output_dir / _relative_output(doc["source_path"])
            out_file.parent.mkdir(parents=True, exist_ok=True)
            content_bytes = content.encode("utf-8")
            out_file.write_bytes(content_bytes)
            file_records.append(
                FileExportRecord(
                    entity_id=doc["source_path"],
                    entity_type="Document",
                    output_path=out_file,
                    sha256=hashlib.sha256(content_bytes).hexdigest(),
                )
            )
        except Exception as exc:  # noqa: BLE001 — collected per-document
            logger.error("Failed to reconstruct document '%s': %s", doc["source_path"], exc)
            errors.append((doc["source_path"], str(exc)))

    covered = _covered_source_docs(store, namespace)
    orphans = _orphan_entity_ids(store, namespace, covered)
    discovered = len(documents)
    if orphans:
        orphan_result = _export_orphans(store, output_dir, orphans, namespace)
        file_records.extend(orphan_result.file_records)
        errors.extend(orphan_result.errors)
        discovered += orphan_result.discovered_count

    file_hashes = {
        str(r.output_path.relative_to(output_dir)).replace("\\", "/"): r.sha256
        for r in file_records
    }
    return CompileResult(
        exported_at=datetime.now(UTC),
        discovered_count=discovered,
        output_dir=output_dir,
        file_records=sorted(file_records, key=lambda r: r.entity_id),
        file_hashes=file_hashes,
        errors=errors,
    )


def _export_orphans(
    store: ox.Store,
    output_dir: Path,
    orphan_ids: set[str],
    namespace: str,
) -> CompileResult:
    """Per-entity card export restricted to the orphan entity subset."""
    full = compile_to_markdown(store, output_dir, namespace=namespace)
    kept = [r for r in full.file_records if r.entity_id in orphan_ids]
    # Remove card files written for entities that are not orphans.
    for record in full.file_records:
        if record.entity_id not in orphan_ids:
            with contextlib.suppress(OSError):
                record.output_path.unlink()
    file_hashes = {
        str(r.output_path.relative_to(output_dir)).replace("\\", "/"): r.sha256 for r in kept
    }
    return CompileResult(
        exported_at=full.exported_at,
        discovered_count=len(kept),
        output_dir=output_dir,
        file_records=kept,
        file_hashes=file_hashes,
        errors=[e for e in full.errors if e[0] in orphan_ids],
    )
