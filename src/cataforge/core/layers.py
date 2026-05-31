"""Override-layer resolution — the single source of truth for asset precedence.

CataForge resolves agents / skills / rules across four conceptual layers,
highest priority first:

1. ``.cataforge/overrides/user/<kind>/``    — personal, upgrade-immune.
2. ``.cataforge/overrides/project/<kind>/`` — team-shared, upgrade-immune.
3. ``.cataforge/<kind>/``                    — framework scaffold (refreshed by
   ``upgrade apply``).
4. package builtins / plugins               — resolved by the individual
   loaders, not here.

The override layers live outside the scaffold manifest, so ``upgrade apply``
never overwrites them. This module only deals with the on-disk override and
scaffold roots (layers 1-3); builtin/plugin resolution stays in the skill and
rules loaders that know how to read package data.

Every consumer (skill loader, rules loader, asset resolver, deploy) derives its
layer ordering from :func:`asset_layer_dirs` so precedence is defined once.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.core.paths import ProjectPaths

# Override layers ordered LOW → HIGH priority. Returned with the scaffold root
# prepended so a simple "later wins" overlay yields the correct winner.
OVERRIDE_LAYERS: tuple[str, ...] = ("project", "user")

# Subdir-per-asset kinds the resolver overlays whole-dir + section-patch.
# Skill-level rules YAML (``skills/<id>/rules/*.yaml``) ride along inside the
# ``skills`` asset for deploy, and are additionally resolved at runtime by
# ``discover_rules``; the top-level ``rules/`` prose dir is not a subdir-asset
# kind and is deployed straight from the scaffold.
ASSET_KINDS: frozenset[str] = frozenset({"agents", "skills"})


def asset_layer_dirs(paths: ProjectPaths, kind: str) -> list[Path]:
    """Existing layer roots for *kind*, ordered LOW → HIGH priority.

    The scaffold root (``.cataforge/<kind>``) comes first, then the project
    and user override roots. Only directories that exist on disk are returned,
    so callers can iterate without per-entry guards. ``kind`` must be one of
    :data:`ASSET_KINDS`.
    """
    if kind not in ASSET_KINDS:
        raise ValueError(f"unknown asset kind {kind!r}; expected one of {sorted(ASSET_KINDS)}")
    roots = [paths.cataforge_dir / kind]
    roots += [paths.override_layer(layer) / kind for layer in OVERRIDE_LAYERS]
    return [r for r in roots if r.is_dir()]


def has_overrides(paths: ProjectPaths) -> bool:
    """Whether any override layer directory exists at all.

    Lets opt-in callers (e.g. deploy) skip the resolve/stage path entirely
    when no project uses overrides — keeping behaviour byte-identical to the
    pre-overrides flow for the common case.
    """
    return paths.overrides_dir.is_dir()
