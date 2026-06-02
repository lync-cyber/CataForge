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

import logging
from collections import OrderedDict
from pathlib import Path

from cataforge.core.layers import asset_layer_dirs
from cataforge.core.paths import ProjectPaths
from cataforge.core.section_patch import apply_section_patch

logger = logging.getLogger("cataforge.runtime.assets.resolver")

_PATCH_SUFFIX = ".patch.md"


def resolve_kind(
    paths: ProjectPaths,
    kind: str,
    dest_dir: Path,
    *,
    plugin_dirs: dict[str, Path] | None = None,
) -> list[str]:
    """Materialise every effective *kind* asset under *dest_dir*.

    Source dirs per asset id, low → high priority: plugin-provided dir (when
    *plugin_dirs* maps the id), then the scaffold and override layers. Returns
    the sorted asset ids written. ``dest_dir/<id>/...`` mirrors the structure
    the deploy mixins expect from ``.cataforge/<kind>/``.
    """
    layers = asset_layer_dirs(paths, kind)
    plugin_dirs = plugin_dirs or {}
    if not layers and not plugin_dirs:
        return []

    ids = set(plugin_dirs) | {d.name for root in layers for d in root.iterdir() if d.is_dir()}
    for asset_id in sorted(ids):
        srcs: list[Path] = []
        if asset_id in plugin_dirs:  # lowest priority — scaffold/overrides win
            srcs.append(plugin_dirs[asset_id])
        srcs += [root / asset_id for root in layers if (root / asset_id).is_dir()]
        _materialize(srcs, dest_dir / asset_id)
    return sorted(ids)


def _materialize(src_dirs: list[Path], dest: Path) -> None:
    """Overlay *src_dirs* (low → high) into *dest*, applying section patches.

    A ``<name>.patch.md`` patches the working ``<name>.md`` overlaid from a
    lower layer. A patch with no such base in any lower layer is an orphan —
    almost always a typo in the patch name (e.g. ``orchestrater.patch.md``).
    Materialising it would write the patch verbatim as a brand-new
    ``<name>.md`` asset; instead the orphan is skipped and logged so the typo
    surfaces rather than silently shipping a bogus asset.
    """
    files: OrderedDict[str, bytes] = OrderedDict()
    for asset_dir in src_dirs:
        for src in sorted(asset_dir.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(asset_dir).as_posix()
            if rel.endswith(_PATCH_SUFFIX):
                base_rel = rel[: -len(_PATCH_SUFFIX)] + ".md"
                if base_rel not in files:
                    logger.warning(
                        "Skipping orphan patch %r in %s: no base %r to patch "
                        "(check the patch filename for a typo).",
                        rel,
                        asset_dir,
                        base_rel,
                    )
                    continue
                base_text = files[base_rel].decode("utf-8")
                patched = apply_section_patch(base_text, src.read_text())
                files[base_rel] = patched.encode("utf-8")
            else:
                files[rel] = src.read_bytes()

    for rel, content in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
