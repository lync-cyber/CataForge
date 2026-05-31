"""Resolve layered assets into a flat, effective tree for deploy.

An asset is one subdirectory of an asset kind (``agents/<id>/``,
``skills/<id>/``). :func:`resolve_kind` overlays every layer
(:func:`cataforge.core.layers.asset_layer_dirs`, low → high priority) for each
asset id and writes the effective files into a destination directory so the
existing deploy mixins — which read a single source dir — transparently see the
merged result.

Two override granularities, applied per file as layers are walked low → high:

* a plain file (``AGENT.md``, ``scripts/foo.py``) **replaces** the same-path
  file from lower layers (whole-file override);
* a ``<name>.patch.md`` **section-patches** the working ``<name>.md`` via
  :func:`cataforge.core.section_patch.apply_section_patch` — overriding matching
  ``## `` sections and appending new ones.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from cataforge.core.layers import asset_layer_dirs
from cataforge.core.paths import ProjectPaths
from cataforge.core.section_patch import apply_section_patch

_PATCH_SUFFIX = ".patch.md"


def resolve_kind(paths: ProjectPaths, kind: str, dest_dir: Path) -> list[str]:
    """Materialise every effective *kind* asset under *dest_dir*.

    Returns the sorted asset ids written. ``dest_dir/<id>/...`` mirrors the
    structure the deploy mixins expect from ``.cataforge/<kind>/``.
    """
    layers = asset_layer_dirs(paths, kind)
    if not layers:
        return []

    ids = sorted({d.name for root in layers for d in root.iterdir() if d.is_dir()})
    for asset_id in ids:
        _materialize(layers, asset_id, dest_dir / asset_id)
    return ids


def _materialize(layers: list[Path], asset_id: str, dest: Path) -> None:
    """Overlay *asset_id* across *layers* (low → high) and write into *dest*."""
    files: OrderedDict[str, bytes] = OrderedDict()
    for root in layers:
        asset_dir = root / asset_id
        if not asset_dir.is_dir():
            continue
        for src in sorted(asset_dir.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(asset_dir).as_posix()
            if rel.endswith(_PATCH_SUFFIX):
                base_rel = rel[: -len(_PATCH_SUFFIX)] + ".md"
                base_text = files.get(base_rel, b"").decode("utf-8")
                patched = apply_section_patch(base_text, src.read_text(encoding="utf-8"))
                files[base_rel] = patched.encode("utf-8")
            else:
                files[rel] = src.read_bytes()

    for rel, content in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
