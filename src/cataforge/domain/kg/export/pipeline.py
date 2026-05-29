"""`compile_to_markdown()` — query → render → write pipeline.

Full export only (no `EntityFilter`, no snapshot, no incremental).
Idempotency rests on three guarantees:

* every SPARQL template ends with `ORDER BY ?sort_key`;
* `hydrator.hydrate_rows()` re-sorts every relation group by
  `(sort_key, entity_id)` so SPARQL join-order drift can't leak in;
* the Jinja2 env uses `StrictUndefined` so an accidental
  `{{ generated_at }}` raises rather than rendering empty.

Together they make `compile_to_markdown()` byte-stable: two runs over
an unchanged store produce the same SHA-256 for every output file
(verified by `tests/kg/test_export.py::test_export_idempotency`).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _term_value,
    assert_safe_iri,
    escape_sparql_literal,
)
from cataforge.domain.kg.export._entity_meta import (
    _RELATION_GROUPS,
    _entity_type_to_doc_type,
    resolve_template,
)
from cataforge.domain.kg.export.hydrator import hydrate_rows
from cataforge.domain.kg.export.registry import SparqlRegistry
from cataforge.domain.kg.export.template_loader import build_jinja_env
from cataforge.domain.kg.export.types import CompileResult, FileExportRecord

if TYPE_CHECKING:
    import pyoxigraph as ox

logger = logging.getLogger(__name__)


def _list_business_entities(store: ox.Store, namespace: str) -> list[tuple[str, str, str]]:
    """Return [(entity_id, sort_key, entity_type)] for every business entity.

    Project is excluded (it has no `cf:sort_key` and is rendered separately
    if needed). Result is ordered by `sort_key` so the export iteration is
    stable.
    """
    assert_safe_iri(namespace)
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?entity_id ?sort_key ?cls WHERE { "
        "?s a ?cls ; cf:entity_id ?entity_id ; cf:sort_key ?sort_key . "
        "FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        "FILTER(?cls != cf:Project) "
        "} ORDER BY ?sort_key ?entity_id"
    )
    out: list[tuple[str, str, str]] = []
    for row in store.query(sparql):
        eid = _term_value(_row_lookup(row, "entity_id"))
        sk = _term_value(_row_lookup(row, "sort_key"))
        cls = _term_value(_row_lookup(row, "cls"))
        if eid is None or cls is None:
            continue
        cls_str = str(cls)
        entity_type = cls_str.rsplit("/", 1)[-1]
        out.append((str(eid), str(sk) if sk is not None else "", entity_type))
    return out


def compile_to_markdown(
    store: ox.Store,
    output_dir: Path,
    *,
    namespace: str = "https://cataforge.dev/ontology/",
) -> CompileResult:
    """Export every business entity in `store` to one Markdown file each.

    Files land under `output_dir/{doc_type}/{entity_id}.md`. Existing
    files are overwritten; this function never deletes — callers wanting
    a clean export should clear `output_dir` first.

    Entities whose class is unknown to the registry (no `<entity_type>.sparql`
    template registered) are skipped with an `errors` entry rather than
    raising.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    registry = SparqlRegistry()
    jinja_env = build_jinja_env()

    namespace = namespace.rstrip("/") + "/"
    entities = _list_business_entities(store, namespace)

    file_records: list[FileExportRecord] = []
    errors: list[tuple[str, str]] = []

    for entity_id, _sort_key, entity_type in entities:
        try:
            sparql_template = registry.get(entity_type)
            sparql_query = sparql_template % {"entity_id": f'"{escape_sparql_literal(entity_id)}"'}
            raw_rows = list(store.query(sparql_query))
            relation_groups = _RELATION_GROUPS.get(entity_type.lower(), {})
            context = hydrate_rows(raw_rows, relation_groups)
            if context is None:
                errors.append((entity_id, "empty SPARQL result"))
                continue

            template = resolve_template(jinja_env, entity_type)
            rendered = template.render(entity=context)

            doc_type = _entity_type_to_doc_type(entity_type)
            out_file = output_dir / doc_type / f"{entity_id}.md"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            content_bytes = rendered.encode("utf-8")
            out_file.write_bytes(content_bytes)

            sha = hashlib.sha256(content_bytes).hexdigest()
            file_records.append(
                FileExportRecord(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    output_path=out_file,
                    sha256=sha,
                )
            )
        except Exception as exc:  # noqa: BLE001 — collected per-entity
            logger.error("Failed to export entity '%s': %s", entity_id, exc)
            errors.append((entity_id, str(exc)))

    file_hashes = {
        str(r.output_path.relative_to(output_dir)).replace("\\", "/"): r.sha256
        for r in file_records
    }

    return CompileResult(
        exported_at=datetime.now(timezone.utc),
        discovered_count=len(entities),
        output_dir=output_dir,
        file_records=sorted(file_records, key=lambda r: r.entity_id),
        file_hashes=file_hashes,
        errors=errors,
    )
