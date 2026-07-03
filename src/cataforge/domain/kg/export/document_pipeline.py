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

from cataforge.domain.kg._quads import XSD_STRING_IRI, _slot_iri
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

# Literal slot recording a Document's last-sync baseline: the byte sha256 of
# the file most recently exported, or of the disk state a graph-side authoring
# write absorbed/superseded. reconcile triages on-disk and freshly-rendered
# bytes against it; finalize overwrites a file freely only while its disk
# bytes still match this baseline.
EXPORTED_CONTENT_HASH_SLOT = "cf:exported_content_hash"


def _list_documents(store: ox.Store, namespace: str) -> list[dict[str, str]]:
    """Return one record per `cf:Document` node carrying a `cf:source_path`.

    A Document without a `source_path` was not derived from a scanned file
    (it cannot be written back), so it is skipped here.
    """
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?doc ?source_path ?doc_type ?source_doc ?frontmatter ?preamble WHERE { "
        "  ?doc a cf:Document ; cf:source_path ?source_path . "
        "  OPTIONAL { ?doc cf:doc_type ?doc_type } "
        "  OPTIONAL { ?doc cf:source_doc ?source_doc } "
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
                "source_doc": _strv(_row_lookup(row, "source_doc")) or "",
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


def render_document(store: ox.Store, namespace: str, doc: dict[str, str]) -> str:
    """Reconstruct one Document's canonical Markdown text from the graph.

    ``doc`` is a record from :func:`_list_documents`. The text is the same
    string :func:`compile_documents` writes to disk, so callers that only need
    the rendered bytes (drift triage) can compare against it without writing a
    file.
    """
    sections = _section_bodies(store, namespace, doc["doc_iri"])
    return _assemble(doc["frontmatter_raw"], doc["preamble_body"], sections)


def _get_exported_hash(store: ox.Store, namespace: str, doc_iri: str) -> str | None:
    """Return the Document's `cf:exported_content_hash` baseline, or None."""
    import pyoxigraph as ox  # noqa: PLC0415

    subject = ox.NamedNode(doc_iri)
    predicate = ox.NamedNode(_slot_iri(EXPORTED_CONTENT_HASH_SLOT, namespace))
    for quad in store.quads_for_pattern(subject, predicate, None, None):
        obj = quad.object
        if isinstance(obj, ox.Literal):
            return str(obj.value)
    return None


def content_equivalent(a: str, b: str) -> bool:
    """Whether two Markdown texts differ only in canonical whitespace form.

    The export emits canonical form (blank-line runs collapsed to one, single
    trailing newline), so a just-ingested source compares equal here even when
    the bytes differ. A semantic difference — the graph holding stale or
    missing content — never normalizes away.
    """

    def _canon(text: str) -> str:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        out: list[str] = []
        blank = False
        for line in lines:
            stripped = line.rstrip()
            if stripped == "":
                if not blank:
                    out.append("")
                blank = True
            else:
                blank = False
                out.append(stripped)
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out)

    return _canon(a) == _canon(b)


def set_exported_hash(store: ox.Store, namespace: str, doc_iri: str, content_hash: str) -> None:
    """Record `content_hash` as the Document's `cf:exported_content_hash` baseline.

    Old quads for the predicate are removed first so the literal stays
    single-valued across re-exports.
    """
    import pyoxigraph as ox  # noqa: PLC0415

    subject = ox.NamedNode(doc_iri)
    predicate = ox.NamedNode(_slot_iri(EXPORTED_CONTENT_HASH_SLOT, namespace))
    for quad in list(store.quads_for_pattern(subject, predicate, None, None)):
        store.remove(quad)
    store.add(
        ox.Quad(subject, predicate, ox.Literal(content_hash, datatype=ox.NamedNode(XSD_STRING_IRI)))
    )


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
    doc_types: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
    backup_dir: Path | None = None,
) -> CompileResult:
    """Reconstruct source Markdown files from the graph.

    Files land at ``output_dir/<source_path without leading "docs/">``.
    Business entities not covered by any Document fall back to per-entity
    cards via :func:`compile_to_markdown` restricted to the orphan subset.

    ``doc_types`` restricts the export to matching Documents (orphan cards
    are skipped under a restricted export). ``dry_run`` computes the per-file
    plan without touching disk or baselines. A file whose on-disk content
    differs from the render, from the last export baseline, *and* is not
    whitespace-equivalent to the render carries changes the graph has not
    absorbed — it is ``blocked`` unless ``force``. Overwritten files are
    copied into ``backup_dir`` first when one is given.
    """
    output_dir = Path(output_dir).resolve()
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    namespace = namespace.rstrip("/") + "/"

    file_records: list[FileExportRecord] = []
    errors: list[tuple[str, str]] = []
    plan: list[tuple[str, str]] = []
    blocked: list[str] = []

    documents = _list_documents(store, namespace)
    if doc_types is not None:
        wanted = set(doc_types)
        documents = [d for d in documents if d["doc_type"] in wanted]
    for doc in documents:
        try:
            content = render_document(store, namespace, doc)
            out_file = output_dir / _relative_output(doc["source_path"])
            content_bytes = content.encode("utf-8")
            disk_bytes = out_file.read_bytes() if out_file.is_file() else None
            if disk_bytes is None:
                status = "new"
            elif disk_bytes == content_bytes:
                status = "unchanged"
            else:
                baseline = _get_exported_hash(store, namespace, doc["doc_iri"])
                disk_hash = hashlib.sha256(disk_bytes).hexdigest()
                safe = (
                    force
                    or (baseline is not None and disk_hash == baseline)
                    or content_equivalent(disk_bytes.decode("utf-8", errors="replace"), content)
                )
                status = "update" if safe else "blocked"
            plan.append((doc["source_path"], status))
            if dry_run:
                continue
            if status == "blocked":
                blocked.append(doc["source_path"])
                continue
            if status == "update" and backup_dir is not None:
                backup_file = backup_dir / _relative_output(doc["source_path"])
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                backup_file.write_bytes(disk_bytes or b"")
            if status != "unchanged":
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_bytes(content_bytes)
            digest = hashlib.sha256(content_bytes).hexdigest()
            set_exported_hash(store, namespace, doc["doc_iri"], digest)
            file_records.append(
                FileExportRecord(
                    entity_id=doc["source_path"],
                    entity_type="Document",
                    output_path=out_file,
                    sha256=digest,
                )
            )
        except Exception as exc:  # noqa: BLE001 — collected per-document
            logger.error("Failed to reconstruct document '%s': %s", doc["source_path"], exc)
            errors.append((doc["source_path"], str(exc)))

    covered = _covered_source_docs(store, namespace)
    orphans = _orphan_entity_ids(store, namespace, covered) if doc_types is None else set()
    discovered = len(documents)
    if orphans and not dry_run:
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
        plan=sorted(plan),
        blocked=sorted(blocked),
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
