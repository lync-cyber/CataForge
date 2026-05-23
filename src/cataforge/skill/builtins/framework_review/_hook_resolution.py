"""Hook script resolution + capability id loading (shared by B5 / B6)."""

from __future__ import annotations

import importlib.resources
from pathlib import Path


def resolve_builtin_hook_dir() -> Path | None:
    """Locate the cataforge.hook.scripts package directory.

    ``importlib.resources.files`` returns a Traversable that's a real
    Path on filesystem-backed installs (editable + wheel). If the
    package is missing or zip-imported we fall back to None — the
    caller treats that as "no builtins available" and any script not
    in custom/ then fails reachability.
    """
    try:
        pkg = importlib.resources.files("cataforge.hook.scripts")
    except (ModuleNotFoundError, TypeError):
        return None
    p = Path(str(pkg))
    return p if p.is_dir() else None


def resolve_hook_script(
    script: str,
    builtin_dir: Path | None,
    custom_dir: Path,
) -> Path | None:
    """Return the .py path for *script*, or None if not found.

    Mirrors the resolution logic in cataforge.hook.bridge so audit and
    deploy stay in lockstep — if this returns None, the deploy will
    also fail to wire the hook.
    """
    if script.startswith("custom:"):
        name = script.removeprefix("custom:")
        candidate = custom_dir / f"{name}.py"
        return candidate if candidate.is_file() else None
    if builtin_dir is None:
        return None
    candidate = builtin_dir / f"{script}.py"
    return candidate if candidate.is_file() else None


def load_capability_ids() -> set[str]:
    """Return CAPABILITY_IDS ∪ EXTENDED_CAPABILITY_IDS, or empty on failure.

    Imports lazily so framework-review still runs on a project where
    cataforge.core.types isn't importable (e.g. older wheel) — the
    matcher_capability check just becomes a no-op.
    """
    try:
        from cataforge.core.types import CAPABILITY_IDS, EXTENDED_CAPABILITY_IDS
    except ImportError:
        return set()
    return set(CAPABILITY_IDS) | set(EXTENDED_CAPABILITY_IDS)


def load_hooks_manifest_names() -> set[str]:
    """Return ``{name}`` for HOOKS_MANIFEST entries, or empty on import failure.

    Lazy import keeps framework-review usable on older wheels that ship
    cataforge without the manifest module — B6-ε just becomes a no-op
    rather than an exception.
    """
    try:
        from cataforge.hook.manifest import manifest_names
    except ImportError:
        return set()
    return set(manifest_names())
