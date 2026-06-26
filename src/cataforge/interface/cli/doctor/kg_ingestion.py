"""Doctor gate: KG ingestion completeness.

Skipped (returns 0) when there are no active doc_types yet or when
the `.cataforge/kg/store/` directory is absent, so downstream projects
that have not opted into KG cutover are not blocked.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.paths import KG_SNAPSHOTS_REL, KG_STORE_REL
from cataforge.domain.docs.loader import DEFAULT_DOC_TYPE_MAP

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


# Lazy-initialized; built on first use from ENTITY_PREFIX_TO_CLASS keys.
_ENTITY_ID_RE: re.Pattern[str] | None = None

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _get_entity_id_re() -> re.Pattern[str]:
    global _ENTITY_ID_RE  # noqa: PLW0603
    if _ENTITY_ID_RE is None:
        from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS  # noqa: PLC0415

        prefixes = "|".join(
            re.escape(p) for p in sorted(ENTITY_PREFIX_TO_CLASS.keys(), key=len, reverse=True)
        )
        _ENTITY_ID_RE = re.compile(rf"\b(?:{prefixes})-\d{{3,}}\b")
    return _ENTITY_ID_RE


def _load_framework_json(cfg: ConfigManager) -> dict[str, Any] | None:
    """Return parsed framework.json for cfg, or None on any failure."""
    try:
        framework = cfg.paths.framework_json
    except AttributeError:
        return None
    if not Path(framework).is_file():
        return None
    try:
        data = read_json(framework)
    except ConfigError:
        return None
    return data if isinstance(data, dict) else None


def _default_kg_active() -> set[str]:
    # Lazy import: `cataforge.domain.kg.__init__` pulls in the pyoxigraph stack, so we
    # only touch it on the framework.json-missing fallback (a KG-active path).
    from cataforge.domain.kg._config import DEFAULT_KG_ACTIVE_DOC_TYPES

    return set(DEFAULT_KG_ACTIVE_DOC_TYPES)


def _project_active_doc_types(cfg: ConfigManager) -> set[str]:
    """Resolve the active doc_type set for cfg."""
    data = _load_framework_json(cfg)
    if data is None:
        return _default_kg_active()
    context_section = data.get("context") or {}
    declared = context_section.get("kg_active_doc_types")
    if isinstance(declared, list) and all(isinstance(d, str) for d in declared):
        return set(declared)
    return _default_kg_active()


def _doc_type_to_subdir(cfg: ConfigManager) -> dict[str, str]:
    """Resolve the doc_type → subdir map (defaults + framework.json override)."""
    data = _load_framework_json(cfg)
    if data is None:
        return dict(DEFAULT_DOC_TYPE_MAP)
    override = (data.get("docs") or {}).get("doc_types") or {}
    merged = dict(DEFAULT_DOC_TYPE_MAP)
    for k, v in override.items():
        if isinstance(k, str) and isinstance(v, str):
            merged[k] = v
    return merged


def _scan_markdown_entity_ids(content: str) -> set[str]:
    """Extract whitelisted entity IDs from markdown, skipping code blocks."""
    body = _FENCED_CODE_RE.sub("", content)
    body = _INLINE_CODE_RE.sub("", body)
    entity_re = _get_entity_id_re()
    return set(entity_re.findall(body))


def _scan_fs_entity_ids(
    project_root: Path, doc_types: set[str], type_map: dict[str, str]
) -> set[str]:
    """Enumerate entity_id strings declared in any active doc_type's markdown sources."""
    found: set[str] = set()
    for doc_type in doc_types:
        subdir = type_map.get(doc_type, doc_type)
        directory = project_root / "docs" / subdir
        if not directory.is_dir():
            continue
        for path in directory.glob("*.md"):
            try:
                content = path.read_text()
            except OSError:
                continue
            found.update(_scan_markdown_entity_ids(content))
    return found


def _fs_relation_endpoint_ids(project_root: Path, doc_types: set[str]) -> set[str]:
    """entity_ids appearing as the subject or object of any extracted relation.

    A relation participant is a graph fact even with no entity node of its own
    (a coverage matrix's TC-id verifies an existing Task), so it is not a
    dangling reference.
    """
    from cataforge.domain.kg.ingest.relation_extract import extract_relations  # noqa: PLC0415
    from cataforge.domain.kg.ingest.scan import scan_business_docs  # noqa: PLC0415

    endpoints: set[str] = set()
    for doc in scan_business_docs(project_root, sorted(doc_types)):
        for rel in extract_relations(doc):
            endpoints.add(rel.subject_entity_id)
            endpoints.add(rel.object_entity_id)
    return endpoints


def _home_doc_type(entity_id: str) -> str | None:
    """Owning doc_type for an entity_id's class, or None for unknown prefixes."""
    from cataforge.domain.kg._config import ENTITY_CLASS_TO_DOC_TYPE  # noqa: PLC0415
    from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS  # noqa: PLC0415

    class_name = ENTITY_PREFIX_TO_CLASS.get(entity_id.split("-", 1)[0])
    if class_name is None:
        return None
    return ENTITY_CLASS_TO_DOC_TYPE.get(class_name)


def _reference_only_summary(ids: set[str]) -> str:
    """Per-prefix count summary like ``TC×71, CR×4, SR×1``."""
    by_prefix: dict[str, int] = {}
    for entity_id in ids:
        prefix = entity_id.split("-", 1)[0]
        by_prefix[prefix] = by_prefix.get(prefix, 0) + 1
    return ", ".join(f"{prefix}×{count}" for prefix, count in sorted(by_prefix.items()))


def _kg_entity_ids(db_path: Path) -> set[str]:
    """Open the store read-only and pull every `cf:entity_id` literal."""
    from cataforge.domain.kg import KGConfig, KnowledgeGraph  # noqa: PLC0415

    config = KGConfig(db_path=db_path)
    with KnowledgeGraph.connect(config, read_only=True) as kg:
        return kg.query.entity_ids()


def _fs_extracted_entities(project_root: Path, doc_types: set[str]) -> list[Any]:
    """All entity definitions the import pipeline would extract from active docs."""
    from cataforge.domain.kg._dispatch import definition_authority  # noqa: PLC0415
    from cataforge.domain.kg.ingest.entity_extract import extract_entities  # noqa: PLC0415
    from cataforge.domain.kg.ingest.scan import scan_business_docs  # noqa: PLC0415

    authority = definition_authority(project_root)
    all_entities: list[Any] = []
    for doc in scan_business_docs(project_root, sorted(doc_types)):
        all_entities.extend(extract_entities(doc, authority=authority))
    return all_entities


def _fs_entity_collisions(all_entities: list[Any]) -> list[Any]:
    """Same-id-defined-across-docs collisions, parsed straight from markdown.

    Mirrors the import-time gate so a store ingested before the gate landed
    (or never re-imported) still surfaces the collapse instead of staying
    falsely green on a set-vs-set comparison that the collapsed node satisfies.
    """
    from cataforge.domain.kg.ingest.entity_extract import (  # noqa: PLC0415
        detect_entity_id_collisions,
    )

    return detect_entity_id_collisions(all_entities)


def _dangling_lines(dangling: set[str], defined_ids: set[str]) -> list[str]:
    """Render dangling references grouped by id prefix.

    A prefix with zero definitions anywhere in the active sources is
    doc_type-activation debt — one summary line per prefix. A prefix that does
    have definitions points at genuinely stale references — those ids stay
    individually listed.
    """
    defined_prefixes = {entity_id.split("-", 1)[0] for entity_id in defined_ids}
    by_prefix: dict[str, list[str]] = {}
    for entity_id in sorted(dangling):
        by_prefix.setdefault(entity_id.split("-", 1)[0], []).append(entity_id)

    lines: list[str] = []
    listed: list[str] = []
    for prefix, ids in sorted(by_prefix.items()):
        if prefix in defined_prefixes:
            listed.extend(ids)
        else:
            sample = ", ".join(ids[:3])
            lines.append(
                f"{len(ids)} {prefix}- id(s) referenced, none defined in "
                f"active sources (e.g. {sample})"
            )
    if listed:
        preview = listed[:5]
        ellipsis = "..." if len(listed) > 5 else ""
        lines.append(f"stale reference(s): {preview}{ellipsis}")
    return lines


def check_kg_ingestion_completeness(cfg: ConfigManager) -> int:
    """Doctor gate — returns failure count for missing KG entity IDs."""
    project_root = Path(cfg.paths.root)
    db_path = project_root / KG_STORE_REL

    if not db_path.exists():
        click.echo(
            "  (no KG store at .cataforge/kg/store — skipping; run "
            "`cataforge context ensure-store` to hydrate it)"
        )
        return 0

    active = _project_active_doc_types(cfg)
    if not active:
        click.echo("  (no active doc_types — skipping)")
        return 0

    all_entities = _fs_extracted_entities(project_root, active)
    collisions = _fs_entity_collisions(all_entities)
    if collisions:
        click.echo(
            f"  FAIL: {len(collisions)} entity_id(s) defined across multiple "
            "documents with diverging content (collapses to one node — silent "
            "data loss):"
        )
        for c in collisions[:5]:
            click.echo(f"    {c.entity_id}:")
            for o in c.occurrences:
                click.echo(f"      {o.source_doc} :: {o.source_section}")
        if len(collisions) > 5:
            click.echo("    ...")
        click.echo(
            "  Keep each entity defined once in its authoritative doc_type and "
            "turn every other occurrence into a reference (xref "
            "`doc_id#§N.ENTITY-ID` or inline code); then re-run "
            "`cataforge kg import`."
        )
        return 1

    type_map = _doc_type_to_subdir(cfg)
    fs_ids = _scan_fs_entity_ids(project_root, active, type_map)
    if not fs_ids:
        click.echo(
            f"  (no entity_ids found in docs/ for active doc_types {sorted(active)} — skipping)"
        )
        return 0

    try:
        kg_ids = _kg_entity_ids(db_path)
    except Exception as exc:  # noqa: BLE001 — opening fail surfaces here
        click.echo(f"  FAIL (could not open KG store at {db_path}: {exc})")
        return 1

    missing = fs_ids - kg_ids
    stale = kg_ids - fs_ids

    # A referenced id with no definition in any active doc_type source cannot
    # be ingested by `kg repair` (it re-reads the same sources) — config
    # guidance, not a repair loop.
    defined_ids = {e.entity_id for e in all_entities}
    dangling = {m for m in missing if m not in defined_ids}
    missing -= dangling

    # Reference-only-by-convention: a dangling id whose prefix is defined
    # nowhere active, whose owning doc_type is already active, and which
    # participates in a relation is a graph endpoint (a coverage matrix's TC
    # verifying an existing Task), not actionable dangling debt — "register the
    # doc_type" is moot and the class is authored as a relation matrix, never
    # heading-defined. Demote to info. Bare prose mentions (not relation
    # endpoints) of a definable class stay flagged.
    defined_prefixes = {e.split("-", 1)[0] for e in defined_ids}
    rel_endpoints = _fs_relation_endpoint_ids(project_root, active)
    reference_only = {
        d
        for d in dangling
        if d.split("-", 1)[0] not in defined_prefixes
        and _home_doc_type(d) in active
        and d in rel_endpoints
    }
    dangling -= reference_only

    if not missing:
        click.echo(f"  OK ({len(fs_ids)} entity_ids reconciled across {sorted(active)})")
    else:
        preview = sorted(missing)[:5]
        ellipsis = "..." if len(missing) > 5 else ""
        click.echo(
            f"  FAIL: KG missing {len(missing)} entity_ids "
            f"({preview}{ellipsis}); run "
            f"`cataforge kg repair --project-root .` to "
            f"reconcile."
        )

    if dangling:
        click.echo(
            f"  WARN: {len(dangling)} entity id(s) referenced in active docs but "
            f"defined in no active doc_type source; "
            f"register the defining doc_type in `context.kg_active_doc_types`, "
            f"or mark the mention as inline code to exempt it."
        )
        for line in _dangling_lines(dangling, defined_ids):
            click.echo(f"    {line}")

    if reference_only:
        click.echo(
            f"  (info: {len(reference_only)} reference-only id(s) participate in "
            f"relations with an active home doc_type — not flagged: "
            f"{_reference_only_summary(reference_only)})"
        )

    if stale:
        preview = sorted(stale)[:5]
        ellipsis = "..." if len(stale) > 5 else ""
        click.echo(
            f"  WARN: KG has {len(stale)} entity_ids no longer in docs/ "
            f"({preview}{ellipsis}); run `cataforge kg repair` "
            f"to prune."
        )

    return 1 if missing else 0


def check_kg_xref_target_integrity(cfg: ConfigManager) -> int:
    """Doctor gate — traceability edges whose target resolves to no entity node.

    Mirrors `kg validate`'s `cf:*-target-exists` shapes. A renamed/deleted
    entity leaves dangling edges that the entity_id-keyed reconcile diff never
    surfaced; this gate makes `kg drift-check`-clean and `doctor`-clean agree.
    """
    project_root = Path(cfg.paths.root)
    db_path = project_root / KG_STORE_REL

    if not db_path.exists():
        click.echo("  (no KG store at .cataforge/kg/store — skipping)")
        return 0

    from cataforge.domain.kg import KGConfig, KnowledgeGraph  # noqa: PLC0415
    from cataforge.domain.kg._sparql_utils import cf_namespace  # noqa: PLC0415
    from cataforge.domain.kg.validate import _check_xref_targets  # noqa: PLC0415

    config = KGConfig(db_path=db_path)
    try:
        with KnowledgeGraph.connect(config, read_only=True) as kg:
            violations = _check_xref_targets(kg.store, cf_namespace(config))
    except Exception as exc:  # noqa: BLE001 — opening fail surfaces here
        click.echo(f"  FAIL (could not open KG store at {db_path}: {exc})")
        return 1

    if not violations:
        click.echo("  OK (no dangling traceability edge targets)")
        return 0

    click.echo(
        f"  FAIL: {len(violations)} traceability edge(s) point at a target missing "
        f"from the graph; run `cataforge kg repair --project-root .` to prune."
    )
    for v in violations[:5]:
        click.echo(f"    {v.entity_id} {v.shape}: {v.message}")
    if len(violations) > 5:
        click.echo("    ...")
    return 1


def check_kg_snapshot_freshness(cfg: ConfigManager) -> int:
    """Doctor gate (graph mode only, WARN) — the durable snapshot must not lag.

    The gitignored store rebuilds from the latest NQuads snapshot on clone
    (`cataforge context ensure-store`), so a snapshot older than the live store
    means uncommitted graph state would be lost. Non-gating (returns 0): it
    nudges the author to `cataforge context finalize`, which refreshes the
    snapshot. Skipped outside graph mode (no snapshot SoT) and when no store
    exists yet (a fresh clone before hydration).
    """
    from cataforge.domain.kg._dispatch import context_mode  # noqa: PLC0415

    project_root = Path(cfg.paths.root)
    if context_mode(project_root) != "graph":
        click.echo("  (not graph mode — skipping)")
        return 0

    db_path = project_root / KG_STORE_REL
    if not db_path.exists():
        click.echo("  (no KG store — skipping; run `cataforge context ensure-store`)")
        return 0

    from cataforge.domain.kg import KGConfig, KnowledgeGraph  # noqa: PLC0415
    from cataforge.domain.kg.snapshot import list_snapshots  # noqa: PLC0415

    config = KGConfig(db_path=db_path)
    try:
        with KnowledgeGraph.connect(config, read_only=True) as kg:
            store_quads = sum(1 for _ in kg.store.quads_for_pattern(None, None, None, None))
    except Exception as exc:  # noqa: BLE001 — opening fail surfaces here
        click.echo(f"  (could not open KG store at {db_path}: {exc} — skipping)")
        return 0

    snapshots = list_snapshots(project_root / KG_SNAPSHOTS_REL)
    if not snapshots:
        click.echo(
            "  WARN: graph store has no NQuads snapshot; a fresh clone cannot "
            "rebuild it — run `cataforge context finalize` to write one."
        )
        return 0

    latest = snapshots[0]
    if latest.quad_count != store_quads:
        click.echo(
            f"  WARN: snapshot stale (store has {store_quads} quads, latest "
            f"snapshot {latest.path.name} has {latest.quad_count}); run "
            f"`cataforge context finalize` to refresh the durable snapshot."
        )
        return 0

    click.echo(f"  OK (snapshot {latest.path.name} matches store: {store_quads} quads)")
    return 0


def check_kg_snapshot_gitignore(cfg: ConfigManager) -> int:
    """Doctor check (graph mode only, WARN) — NQuads snapshots must stay tracked.

    In graph mode the gitignored store rebuilds from the committed snapshot on
    clone, so a project-root .gitignore that also excludes the snapshots dir
    silently drops the graph's only durable artifact. ``.cataforge/.gitignore``
    keeps snapshots tracked; this catches a root rule that overrides it.
    Advisory (returns 0); skipped outside graph mode and off a git work-tree.
    """
    import shutil  # noqa: PLC0415

    from cataforge.domain.kg._dispatch import context_mode  # noqa: PLC0415

    project_root = Path(cfg.paths.root)
    if context_mode(project_root) != "graph":
        click.echo("  (not graph mode — skipping)")
        return 0
    if shutil.which("git") is None:
        click.echo("  git not on PATH — skipped.")
        return 0

    from cataforge.application.services.git_hygiene import GitWorkTree  # noqa: PLC0415

    git = GitWorkTree(project_root)
    if not git.is_inside_work_tree():
        click.echo("  not a git work-tree — skipped.")
        return 0

    probe = (KG_SNAPSHOTS_REL / "latest.nq").as_posix()
    if git.path_is_ignored(probe):
        click.echo(
            f"  WARN: {KG_SNAPSHOTS_REL.as_posix()} is git-ignored, but graph mode "
            f"rebuilds the store from the committed NQuads snapshot on clone — the "
            f"graph's only durable artifact would be lost. Drop the .cataforge/kg "
            f"(or kg/snapshots) rule from the project-root .gitignore; "
            f".cataforge/.gitignore already tracks snapshots and ignores only the store."
        )
        return 0

    click.echo("  OK — NQuads snapshots are tracked.")
    return 0


__all__ = [
    "check_kg_ingestion_completeness",
    "check_kg_snapshot_freshness",
    "check_kg_snapshot_gitignore",
    "check_kg_xref_target_integrity",
]
