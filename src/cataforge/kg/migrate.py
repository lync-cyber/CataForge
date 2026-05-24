"""One-shot migration: ``docs/.doc-index.json`` → KG.

The big-bang cutover documented in §2.7 of the design note. The previous
graph (if any) is rotated aside to ``.doc-graph.bak.<UTC-stamp>/`` before
the new one is written, so ``--rollback`` can restore the most recent
backup deterministically.

Validation runs after ingest as a *warning*, not a hard gate: legacy
docs may have small SHACL violations on first ingest, and forcing a fix
before any data lands defeats the cutover's "ship a working migration
even if not perfect" intent. Strict gating moves to ``cataforge doctor``
once the migration baseline stabilises (see design §6.4 / Wave D)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cataforge.kg.ingest.markdown import IngestResult, ingest_markdown
from cataforge.kg.ontology import load_ontology, load_shapes
from cataforge.kg.reasoning import infer
from cataforge.kg.reasoning import validate as reasoning_validate
from cataforge.kg.store import RDFLibStore, graph_dir_for

INDEX_PATH = Path("docs/.doc-index.json")
BACKUP_DIRNAME_PREFIX = ".doc-graph.bak."


class MigrationError(RuntimeError):
    """Raised for migration-time failures (missing project root, IO errors)."""


@dataclass
class MigrationReport:
    """Summary of a single ``migrate()`` invocation."""

    files_processed: int = 0
    files_skipped: int = 0
    triples_written: int = 0
    inferred_triples: int = 0
    per_file: dict[str, int] = field(default_factory=dict)
    skipped_files: list[str] = field(default_factory=list)
    shacl_conforms: bool = True
    shacl_violation_count: int = 0
    shacl_report_text: str = ""
    backup_path: Path | None = None
    rolled_back_from: Path | None = None

    def format(self) -> str:
        """Render a human-readable plaintext summary suitable for CLI output."""
        lines = [
            f"files processed : {self.files_processed}",
            f"files skipped   : {self.files_skipped}",
            f"triples written : {self.triples_written}",
            f"inferred triples: {self.inferred_triples}",
        ]
        if self.backup_path:
            lines.append(f"backup          : {self.backup_path}")
        if self.rolled_back_from:
            lines.append(f"rolled back from: {self.rolled_back_from}")
        if self.files_processed:
            lines.append("")
            lines.append("SHACL validation (warning only):")
            lines.append(
                f"  conforms       : {self.shacl_conforms}",
            )
            lines.append(
                f"  violation count: {self.shacl_violation_count}",
            )
            if self.shacl_violation_count and self.shacl_report_text:
                preview = "\n    ".join(
                    self.shacl_report_text.splitlines()[:8],
                )
                lines.append(f"  first lines:\n    {preview}")
        if self.skipped_files:
            lines.append("")
            lines.append("orphans (no frontmatter id):")
            for f in self.skipped_files:
                lines.append(f"  - {f}")
        return "\n".join(lines)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _list_backups(project_root: Path) -> list[Path]:
    docs_dir = project_root.resolve() / "docs"
    if not docs_dir.is_dir():
        return []
    return sorted(
        (p for p in docs_dir.iterdir() if p.is_dir()
         and p.name.startswith(BACKUP_DIRNAME_PREFIX)),
        key=lambda p: p.name,
    )


def _backup_existing_graph(project_root: Path) -> Path | None:
    """Rotate ``.doc-graph/`` aside under a timestamped backup directory."""
    gdir = graph_dir_for(project_root)
    if not gdir.is_dir():
        return None
    backup = gdir.parent / f"{BACKUP_DIRNAME_PREFIX}{_utc_stamp()}"
    shutil.move(str(gdir), str(backup))
    return backup


def _files_from_index(project_root: Path) -> list[Path]:
    """Read ``docs/.doc-index.json`` and return absolute file paths in order.

    Falls back to a ``docs/**/*.md`` glob when the index is missing — keeps
    migration usable on fresh projects that haven't run ``docs index`` yet."""
    root = project_root.resolve()
    index_file = root / INDEX_PATH
    if index_file.is_file():
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MigrationError(
                f"Malformed {INDEX_PATH}: {exc.msg} at line {exc.lineno}",
            ) from exc
        documents = data.get("documents") or {}
        rels = [
            str(entry.get("file_path", "")).strip()
            for entry in documents.values()
        ]
        return [root / r for r in rels if r and (root / r).is_file()]
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        return []
    return sorted(docs_dir.glob("**/*.md"))


def _ingest_all(
    project_root: Path, files: list[Path],
) -> tuple[list[IngestResult], list[Path]]:
    """Two-pass ingest: pass 1 collects cross-doc IDs, pass 2 resolves them."""
    pass1 = [ingest_markdown(f, project_root=project_root) for f in files]
    global_iris: dict[str, str] = {}
    for r in pass1:
        for it in r.items:
            global_iris.setdefault(it.display_id, it.iri)

    pass2: list[IngestResult] = []
    skipped: list[Path] = []
    for f in files:
        r = ingest_markdown(
            f, project_root=project_root, known_item_iris=global_iris,
        )
        if r.document is None:
            skipped.append(f)
        else:
            pass2.append(r)
    return pass2, skipped


def migrate(
    project_root: str | Path,
    *,
    rollback: bool = False,
    validate: bool = True,
) -> MigrationReport:
    """Perform the cutover or restore the most recent backup.

    Parameters
    ----------
    project_root : str | Path
        Repo root (the dir that contains ``docs/`` and ``.cataforge/``).
    rollback : bool
        When True, ignore ingestion and restore ``.doc-graph/`` from the
        most-recent ``.doc-graph.bak.<stamp>/`` directory. The current
        ``.doc-graph/`` is moved aside under a fresh backup stamp first
        so a forward-then-rollback sequence is reversible.
    validate : bool
        Run SHACL validation after the new graph is persisted. Failures
        are reported as warnings — the migration still succeeds.
    """
    root = Path(project_root).resolve()

    if rollback:
        return _do_rollback(root)

    files = _files_from_index(root)
    results, skipped = _ingest_all(root, files)

    backup = _backup_existing_graph(root)

    store = RDFLibStore()
    store.load(root)
    triple_count = 0
    per_file: dict[str, int] = {}
    for r in results:
        store.add(r.triples)
        if r.document is not None:
            per_file[r.document.file_path] = len(r.triples)
            triple_count += len(r.triples)
    store.persist()

    onto = load_ontology(root, include_l3=True, strict=False)
    derived = infer(store._dataset.default_graph, onto)
    inferred_count = store.apply_inference(derived)
    if inferred_count:
        store.persist()

    report = MigrationReport(
        files_processed=len(results),
        files_skipped=len(skipped),
        triples_written=triple_count,
        inferred_triples=inferred_count,
        per_file=per_file,
        skipped_files=[
            str(p.resolve().relative_to(root)).replace("\\", "/")
            for p in skipped
        ],
        backup_path=backup,
    )

    if validate and results:
        shapes_graph = load_shapes(root, include_l3=True, strict=True)
        # Materialise shapes to a temp .ttl so reasoning.validate can pass a path.
        tmp_shapes = graph_dir_for(root) / "_shapes.tmp.ttl"
        shapes_graph.serialize(destination=str(tmp_shapes), format="turtle")
        try:
            vr = reasoning_validate(store, shape_graph=tmp_shapes)
        finally:
            tmp_shapes.unlink(missing_ok=True)
        report.shacl_conforms = vr.conforms
        report.shacl_violation_count = vr.violation_count
        report.shacl_report_text = vr.results_text

    return report


def _do_rollback(project_root: Path) -> MigrationReport:
    backups = _list_backups(project_root)
    if not backups:
        raise MigrationError(
            f"No backups found under {project_root / 'docs'} — nothing to roll back.",
        )
    latest = backups[-1]
    gdir = graph_dir_for(project_root)

    rotated: Path | None = None
    if gdir.is_dir():
        rotated = gdir.parent / f"{BACKUP_DIRNAME_PREFIX}{_utc_stamp()}.preroll"
        shutil.move(str(gdir), str(rotated))

    shutil.move(str(latest), str(gdir))

    return MigrationReport(
        files_processed=0,
        files_skipped=0,
        triples_written=0,
        backup_path=rotated,
        rolled_back_from=latest,
    )
