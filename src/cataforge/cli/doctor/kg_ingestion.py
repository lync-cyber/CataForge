"""Doctor gate: KG ingestion completeness.

Task 6 §6.4.x — once a doc_type is active in `KGConfig.kg_active_doc_types`,
every entity discoverable on the filesystem must also be present in the
KG. A missing entity silently returns `None` from `kg.query.*`, which
under the full-cutover model (Task 7 §7.1) would mask coverage gaps.

Severity is ERROR (contributes to the doctor exit code) for missing
entities. Stale entries — KG-present but FS-absent — surface as WARN
prints that do *not* fail the gate; they signal cleanup work for
`cataforge kg validate --fix-orphans` but are not a correctness hazard.

Skipped (returns 0) when there are no active doc_types yet or when
the `.cataforge/kg/store/` directory is absent, so downstream projects
that have not opted into KG cutover are not blocked.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


_DEFAULT_KG_ACTIVE = {"prd", "arch", "test"}
_ENTITY_ID_RE = re.compile(r"\b([A-Z]+-\d{3,})\b")


def _project_active_doc_types(cfg: ConfigManager) -> set[str]:
    """Resolve the active doc_type set for `cfg`.

    Lookup order:
        1. `.cataforge/framework.json` ``kg.kg_active_doc_types`` list, if present
        2. Built-in Alpha default (prd / arch / test)
    """
    try:
        framework = cfg.paths.framework_json
    except AttributeError:
        return set(_DEFAULT_KG_ACTIVE)
    if not Path(framework).is_file():
        return set(_DEFAULT_KG_ACTIVE)
    try:
        import json

        data = json.loads(Path(framework).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set(_DEFAULT_KG_ACTIVE)
    kg_section = data.get("kg") or {}
    declared = kg_section.get("kg_active_doc_types")
    if isinstance(declared, list) and all(isinstance(d, str) for d in declared):
        return set(declared)
    return set(_DEFAULT_KG_ACTIVE)


def _doc_type_to_subdir(cfg: ConfigManager) -> dict[str, str]:
    """Mirror :func:`cataforge.docs.loader._load_doc_type_map` without
    importing it (keeps doctor module lightweight + decoupled).
    """
    defaults = {
        "prd": "prd",
        "arch": "arch",
        "ui-spec": "ui-spec",
        "dev-plan": "dev-plan",
        "test-report": "test-report",
        "test": "test-report",
        "deploy-spec": "deploy-spec",
        "research": "research",
        "changelog": "changelog",
        "brief": "brief",
    }
    try:
        framework = cfg.paths.framework_json
    except AttributeError:
        return defaults
    if not Path(framework).is_file():
        return defaults
    try:
        import json

        data = json.loads(Path(framework).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaults
    override = (data.get("docs") or {}).get("doc_types") or {}
    merged = dict(defaults)
    for k, v in override.items():
        if isinstance(k, str) and isinstance(v, str):
            merged[k] = v
    return merged


def _scan_fs_entity_ids(
    project_root: Path, doc_types: set[str], type_map: dict[str, str]
) -> set[str]:
    """Enumerate entity_id strings declared in any active doc_type's
    Markdown sources under ``docs/<subdir>/*.md``.
    """
    found: set[str] = set()
    for doc_type in doc_types:
        subdir = type_map.get(doc_type, doc_type)
        directory = project_root / "docs" / subdir
        if not directory.is_dir():
            continue
        for path in directory.glob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for match in _ENTITY_ID_RE.finditer(content):
                found.add(match.group(1))
    return found


def _kg_entity_ids(db_path: Path) -> set[str]:
    """Open the store read-only and pull every `cf:entity_id` literal."""
    from cataforge.kg import KGConfig, KnowledgeGraph  # noqa: PLC0415

    config = KGConfig(db_path=db_path)
    with KnowledgeGraph.connect(config) as kg:
        return kg.query.entity_ids()


def check_kg_ingestion_completeness(cfg: ConfigManager) -> int:
    """Doctor gate — HARD FAIL when FS entity IDs are missing from KG.

    Returns the number of failures contributed to the doctor exit code.
    Per Task 7 §7.1 sub-PR 5 (and the explicit user decision recorded
    in [README §User decisions]), this gate ships at ERROR severity
    without a WARN-to-ERROR promotion period.
    """
    project_root = Path(cfg.paths.root)
    db_path = project_root / ".cataforge" / "kg" / "store"

    if not db_path.exists():
        click.echo(
            "  (no KG store at .cataforge/kg/store — skipping; "
            "run `cataforge kg init` to enable)"
        )
        return 0

    active = _project_active_doc_types(cfg)
    if not active:
        click.echo("  (no active doc_types — skipping)")
        return 0

    type_map = _doc_type_to_subdir(cfg)
    fs_ids = _scan_fs_entity_ids(project_root, active, type_map)
    if not fs_ids:
        click.echo(
            f"  (no entity_ids found in docs/ for active doc_types "
            f"{sorted(active)} — skipping)"
        )
        return 0

    try:
        kg_ids = _kg_entity_ids(db_path)
    except Exception as exc:  # noqa: BLE001 — opening fail surfaces here
        click.echo(f"  FAIL (could not open KG store at {db_path}: {exc})")
        return 1

    missing = fs_ids - kg_ids
    stale = kg_ids - fs_ids

    if not missing:
        click.echo(
            f"  OK ({len(fs_ids)} entity_ids reconciled across "
            f"{sorted(active)})"
        )
    else:
        preview = sorted(missing)[:5]
        ellipsis = "..." if len(missing) > 5 else ""
        click.echo(
            f"  FAIL: KG missing {len(missing)} entity_ids "
            f"({preview}{ellipsis}); run "
            f"`cataforge kg import docs/ --on-conflict=overwrite` to "
            f"reconcile."
        )

    if stale:
        preview = sorted(stale)[:5]
        ellipsis = "..." if len(stale) > 5 else ""
        click.echo(
            f"  WARN: KG has {len(stale)} entity_ids no longer in docs/ "
            f"({preview}{ellipsis}); run `cataforge kg validate "
            f"--fix-orphans` to prune."
        )

    return 1 if missing else 0


__all__ = ["check_kg_ingestion_completeness"]
