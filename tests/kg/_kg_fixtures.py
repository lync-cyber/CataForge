"""Shared, cached scaffolding for KG tests that need an ingested project.

Building the vertical-slice project's graph — copy the fixture docs, init an
oxigraph store, run the ingest codemod — costs ~1s. Tests that only need a
populated graph to then probe reconcile / doctor / compare paid that cost
once per test, which dominated the unit-suite wall clock.

A RocksDB store directory is relocatable, so the ingested project is built
once per (process, variant) and each call hands back a fresh ``copytree`` of
the pre-populated store — ~30x cheaper than re-ingesting, and every caller
still mutates an isolated copy. Under ``-n auto`` each xdist worker is its
own process and builds its own template once; ``atexit`` removes it.
"""

from __future__ import annotations

import atexit
import gc
import hashlib
import shutil
import tempfile
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def hx(seed: str) -> str:
    """Deterministic sha256-hex content hash from a short readable seed.

    The write layer enforces the 64-hex content-hash contract; tests keep
    their readable seeds and derive a valid digest from them.
    """
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


_KG_ACTIVE_DOC_TYPES = {"prd", "arch", "test"}

_templates: dict[str, Path] = {}
_template_root: Path | None = None


def _ingest(project_root: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types=_KG_ACTIVE_DOC_TYPES,
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    del handle
    gc.collect()
    invalidate_cache()


def _template(variant: str) -> Path:
    global _template_root
    if variant not in _templates:
        if _template_root is None:
            _template_root = Path(tempfile.mkdtemp(prefix="kg-template-"))
            atexit.register(shutil.rmtree, _template_root, ignore_errors=True)
        proj = _template_root / variant / "proj"
        shutil.copytree(FIXTURE_ROOT / variant, proj)
        _ingest(proj)
        _templates[variant] = proj
    return _templates[variant]


def setup_project_with_kg(tmp_path: Path, variant: str = "waterfall") -> Path:
    """Return a fresh, pre-ingested project rooted at ``tmp_path / 'proj'``.

    Drop-in for the former per-file helper of the same shape; the ingest is
    served from a per-process template cache, the copy is isolated per call.
    """
    project_root = tmp_path / "proj"
    shutil.copytree(_template(variant), project_root)
    return project_root
