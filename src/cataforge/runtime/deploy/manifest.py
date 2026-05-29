"""Deploy ownership manifest.

Records every IDE-visible path the current ``cataforge deploy`` writes,
links, or merges so the next deploy's prune step can distinguish
*CataForge-owned* artefacts from *user-authored* ones.

Why this exists: prior to this manifest, ``deploy_commands`` and
``deploy_skills`` pruned anything in the target directory that lacked a
counterpart in source. That destroyed:

* hand-authored slash commands the user added under ``.claude/commands/``
* per-project skills under ``.claude/skills/``
* the git-tracked dogfood wrapper ``.claude/commands/framework-issue-resolve.md``
  whose body intentionally has no source under ``.cataforge/commands/``

The manifest gives prune a sharper rule: delete only what was in the
*previous* manifest, never what was just on disk. Items the user authored
were never recorded, so they survive every redeploy.

Layout: ``.cataforge/.deploy-manifest.json`` (gitignored, project-local).
The first deploy on a project that predates this file writes a manifest
but does not prune — there is no prior record to scope deletions against,
so the safe behaviour is "trust the user". Legacy orphans that survive
the first manifest-aware deploy can be cleaned with
``cataforge deploy --rebuild`` (P3) or by hand.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.paths import DEPLOY_MANIFEST_REL

_MANIFEST_VERSION = 1


class DeployManifest:
    """Append-only collector for a single deploy pass.

    Adapters call :meth:`record` for every path they write/link. The
    deployer hands the populated manifest to :func:`save_manifest` at
    the end of the run.

    Path strings are normalised to POSIX style (forward slashes) so the
    manifest is portable across Windows and Unix — comparing
    ``.claude/agents/foo.md`` against ``.claude\\agents\\foo.md`` would
    miss every Windows orphan otherwise.
    """

    __slots__ = ("platform_id", "_paths")

    def __init__(self, platform_id: str) -> None:
        self.platform_id = platform_id
        self._paths: set[str] = set()

    def record(self, rel_path: str | Path) -> None:
        s = str(rel_path).replace("\\", "/").strip("/")
        if s:
            self._paths.add(s)

    def record_many(self, paths: Iterable[str | Path]) -> None:
        for p in paths:
            self.record(p)

    @property
    def owned(self) -> set[str]:
        """A frozen snapshot of the paths recorded so far."""
        return set(self._paths)

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_version": _MANIFEST_VERSION,
            "platform": self.platform_id,
            "owned_paths": sorted(self._paths),
        }


def load_prior_manifest(project_root: Path) -> set[str]:
    """Return paths the previous deploy recorded — empty set if none.

    Empty-on-missing is the load-bearing contract: it teaches prune to
    treat a fresh project (no manifest) as "I own nothing yet" so legacy
    files that predate the manifest stay put on the first manifest-aware
    deploy.
    """
    path = project_root / DEPLOY_MANIFEST_REL
    if not path.is_file():
        return set()
    try:
        data = read_json(path)
    except ConfigError:
        return set()
    if not isinstance(data, dict):
        return set()
    owned = data.get("owned_paths")
    if not isinstance(owned, list):
        return set()
    return {str(p) for p in owned if isinstance(p, str)}


def load_prior_manifest_platform(project_root: Path) -> str | None:
    """Return the ``platform`` id the previous deploy recorded, or ``None``.

    Used by ``--rebuild`` to refuse to wholesale-purge paths whose
    ownership stake belongs to a different platform than the one we're
    deploying now — see :meth:`Deployer._rebuild_purge`.
    """
    path = project_root / DEPLOY_MANIFEST_REL
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except ConfigError:
        return None
    if not isinstance(data, dict):
        return None
    platform = data.get("platform")
    return str(platform) if isinstance(platform, str) else None


def save_manifest(project_root: Path, manifest: DeployManifest) -> None:
    """Persist *manifest* to ``.cataforge/.deploy-manifest.json``."""
    path = project_root / DEPLOY_MANIFEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n"
    path.write_text(payload, encoding="utf-8")


def manifest_path(project_root: Path) -> Path:
    """Where the manifest lives. Exposed for ``--rebuild`` / doctor."""
    return project_root / DEPLOY_MANIFEST_REL
