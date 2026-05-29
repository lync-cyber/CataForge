"""Doctor gate: KG ingestion completeness.

Skipped (returns 0) when there are no active doc_types yet or when
the `.cataforge/kg/store/` directory is absent, so downstream projects
that have not opted into KG cutover are not blocked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


# Lazy-initialized; built on first use from ENTITY_PREFIX_TO_CLASS keys.
_ENTITY_ID_RE: re.Pattern[str] | None = None

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _get_entity_id_re() -> re.Pattern[str]:
    global _ENTITY_ID_RE  # noqa: PLW0603
    if _ENTITY_ID_RE is None:
        from cataforge.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS  # noqa: PLC0415

        prefixes = "|".join(
            re.escape(p) for p in sorted(ENTITY_PREFIX_TO_CLASS.keys(), key=len, reverse=True)
        )
        _ENTITY_ID_RE = re.compile(rf"\b(?:{prefixes})-\d{{3,}}\b")
    return _ENTITY_ID_RE


def _load_framework_json(cfg: ConfigManager) -> dict | None:
    """Return parsed framework.json for cfg, or None on any failure."""
    try:
        framework = cfg.paths.framework_json
    except AttributeError:
        return None
    if not Path(framework).is_file():
        return None
    try:
        return json.loads(Path(framework).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _default_kg_active() -> set[str]:
    # Lazy import: `cataforge.kg.__init__` pulls in the pyoxigraph stack, so we
    # only touch it on the framework.json-missing fallback (a KG-active path).
    from cataforge.kg._config import DEFAULT_KG_ACTIVE_DOC_TYPES

    return set(DEFAULT_KG_ACTIVE_DOC_TYPES)


def _project_active_doc_types(cfg: ConfigManager) -> set[str]:
    """Resolve the active doc_type set for cfg."""
    data = _load_framework_json(cfg)
    if data is None:
        return _default_kg_active()
    kg_section = data.get("kg") or {}
    declared = kg_section.get("kg_active_doc_types")
    if isinstance(declared, list) and all(isinstance(d, str) for d in declared):
        return set(declared)
    return _default_kg_active()


def _doc_type_to_subdir(cfg: ConfigManager) -> dict[str, str]:
    """Mirror cataforge.docs.loader._load_doc_type_map without importing it."""
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
    data = _load_framework_json(cfg)
    if data is None:
        return defaults
    override = (data.get("docs") or {}).get("doc_types") or {}
    merged = dict(defaults)
    for k, v in override.items():
        if isinstance(k, str) and isinstance(v, str):
            merged[k] = v
    return merged


def _extract_frontmatter_id(content: str) -> str | None:
    """Return the `id:` value from YAML front matter, or None."""
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    fm_block = content[3:end]
    for line in fm_block.splitlines():
        stripped = line.strip()
        if stripped.startswith("id:"):
            value = stripped[3:].strip().strip('"').strip("'")
            return value if value else None
    return None


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
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fm_id = _extract_frontmatter_id(content)
            if fm_id:
                found.add(fm_id)
            else:
                found.update(_scan_markdown_entity_ids(content))
    return found


def _kg_entity_ids(db_path: Path) -> set[str]:
    """Open the store read-only and pull every `cf:entity_id` literal."""
    from cataforge.kg import KGConfig, KnowledgeGraph  # noqa: PLC0415

    config = KGConfig(db_path=db_path)
    with KnowledgeGraph.connect(config) as kg:
        return kg.query.entity_ids()


def check_kg_ingestion_completeness(cfg: ConfigManager) -> int:
    """Doctor gate — returns failure count for missing KG entity IDs."""
    project_root = Path(cfg.paths.root)
    db_path = project_root / ".cataforge" / "kg" / "store"

    if not db_path.exists():
        click.echo(
            "  (no KG store at .cataforge/kg/store — skipping; run `cataforge kg init` to enable)"
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

    if stale:
        preview = sorted(stale)[:5]
        ellipsis = "..." if len(stale) > 5 else ""
        click.echo(
            f"  WARN: KG has {len(stale)} entity_ids no longer in docs/ "
            f"({preview}{ellipsis}); run `cataforge kg repair` "
            f"to prune."
        )

    return 1 if missing else 0


__all__ = ["check_kg_ingestion_completeness"]
