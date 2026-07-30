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
from cataforge.utils.atomic_write import atomic_write_text

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

    __slots__ = ("platform_id", "_paths", "source_digest", "package_version")

    def __init__(self, platform_id: str) -> None:
        self.platform_id = platform_id
        self._paths: set[str] = set()
        # Drift baselines, set by the deployer just before save_manifest.
        self.source_digest: str | None = None
        self.package_version: str | None = None

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
        d: dict[str, object] = {
            "manifest_version": _MANIFEST_VERSION,
            "platform": self.platform_id,
            "owned_paths": sorted(self._paths),
        }
        if self.source_digest is not None:
            d["source_digest"] = self.source_digest
        if self.package_version is not None:
            d["package_version"] = self.package_version
        return d


def _owned_paths_from_file(path: Path) -> set[str]:
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


def load_prior_manifest(project_root: Path) -> set[str]:
    """Union of every platform's recorded ownership (legacy slot included).

    Empty-on-missing is the load-bearing contract: it teaches prune to
    treat a fresh project (no manifest) as "I own nothing yet" so legacy
    files that predate the manifest stay put on the first manifest-aware
    deploy.
    """
    owned: set[str] = set()
    for platform_id in recorded_platforms(project_root):
        owned |= _owned_paths_from_file(platform_manifest_path(project_root, platform_id))
    owned |= _owned_paths_from_file(project_root / DEPLOY_MANIFEST_REL)
    return owned


# ---- per-platform layout (.cataforge/state/deploy/<platform>/) ----


def deploy_state_root(project_root: Path) -> Path:
    return project_root / ".cataforge" / "state" / "deploy"


def platform_deploy_dir(project_root: Path, platform_id: str) -> Path:
    return deploy_state_root(project_root) / platform_id


def platform_manifest_path(project_root: Path, platform_id: str) -> Path:
    return platform_deploy_dir(project_root, platform_id) / "manifest.json"


def platform_state_path(project_root: Path, platform_id: str) -> Path:
    return platform_deploy_dir(project_root, platform_id) / "state.json"


def platform_capability_report_path(project_root: Path, platform_id: str) -> Path:
    return platform_deploy_dir(project_root, platform_id) / "capability-report.json"


def recorded_platforms(project_root: Path) -> list[str]:
    """Platforms with a per-platform deploy record (sorted, no legacy)."""
    root = deploy_state_root(project_root)
    if not root.is_dir():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir()
        and ((child / "state.json").is_file() or (child / "manifest.json").is_file())
    )


def deployed_platforms(project_root: Path) -> list[str]:
    """Every platform with a deploy record — per-platform layout first,
    plus the legacy single-slot ``.deploy-state`` if not yet migrated."""
    platforms = recorded_platforms(project_root)
    legacy = _legacy_platform(project_root)
    if legacy and legacy not in platforms:
        platforms.append(legacy)
    return platforms


def _legacy_platform(project_root: Path) -> str | None:
    state_path = project_root / ".cataforge" / ".deploy-state"
    if not state_path.is_file():
        return None
    try:
        data = read_json(state_path)
    except ConfigError:
        return None
    platform = data.get("platform") if isinstance(data, dict) else None
    return str(platform) if isinstance(platform, str) and platform else None


def load_prior_manifest_for(project_root: Path, platform_id: str) -> set[str]:
    """Ownership recorded by *platform_id*'s previous deploy.

    Falls back to the legacy single-slot manifest when the per-platform
    record does not exist yet and the legacy slot belongs to this platform.
    """
    per_platform = platform_manifest_path(project_root, platform_id)
    if per_platform.is_file():
        return _owned_paths_from_file(per_platform)
    if _legacy_platform(project_root) == platform_id or (
        load_prior_manifest_platform(project_root) == platform_id
    ):
        return _owned_paths_from_file(project_root / DEPLOY_MANIFEST_REL)
    return set()


def load_other_platform_owned(project_root: Path, platform_id: str) -> set[str]:
    """Union of every OTHER platform's recorded ownership.

    Prune protection set: a path co-owned by another platform must survive
    this platform's prune (the last owner deletes it on its own deploy).
    """
    owned: set[str] = set()
    for other in recorded_platforms(project_root):
        if other == platform_id:
            continue
        owned |= _owned_paths_from_file(platform_manifest_path(project_root, other))
    legacy_platform = _legacy_platform(project_root) or load_prior_manifest_platform(project_root)
    if legacy_platform and legacy_platform != platform_id:
        owned |= _owned_paths_from_file(project_root / DEPLOY_MANIFEST_REL)
    return owned


def load_prior_baseline_for(project_root: Path, platform_id: str) -> tuple[str | None, str | None]:
    """Drift baseline recorded by *platform_id*'s previous deploy."""
    path = platform_manifest_path(project_root, platform_id)
    if not path.is_file():
        if _legacy_platform(project_root) == platform_id:
            return load_prior_baseline(project_root)
        return None, None
    try:
        data = read_json(path)
    except ConfigError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    digest = data.get("source_digest")
    version = data.get("package_version")
    return (
        digest if isinstance(digest, str) else None,
        version if isinstance(version, str) else None,
    )


def save_platform_manifest(project_root: Path, manifest: DeployManifest) -> None:
    """Persist *manifest* into the per-platform layout (atomic)."""
    path = platform_manifest_path(project_root, manifest.platform_id)
    payload = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(path, payload)


def write_platform_state(project_root: Path, platform_id: str, package_version: str) -> None:
    path = platform_state_path(project_root, platform_id)
    payload = json.dumps(
        {"platform": platform_id, "package_version": package_version},
        indent=2,
        ensure_ascii=False,
    )
    atomic_write_text(path, payload + "\n")


def migrate_legacy_deploy_records(project_root: Path) -> list[str]:
    """Move the single-slot ``.deploy-state``/``.deploy-manifest.json`` into
    the per-platform layout. Idempotent; returns action lines."""
    actions: list[str] = []
    legacy_platform = _legacy_platform(project_root) or load_prior_manifest_platform(project_root)
    legacy_state = project_root / ".cataforge" / ".deploy-state"
    legacy_manifest = project_root / DEPLOY_MANIFEST_REL
    if legacy_platform:
        manifest_dst = platform_manifest_path(project_root, legacy_platform)
        if legacy_manifest.is_file() and not manifest_dst.is_file():
            manifest_dst.parent.mkdir(parents=True, exist_ok=True)
            manifest_dst.write_bytes(legacy_manifest.read_bytes())
            actions.append(f"migrated deploy manifest → {manifest_dst}")
        state_dst = platform_state_path(project_root, legacy_platform)
        if not state_dst.is_file():
            _, version = load_prior_baseline(project_root)
            write_platform_state(project_root, legacy_platform, version or "")
            actions.append(f"migrated deploy state → {state_dst}")
    for legacy in (legacy_state, legacy_manifest):
        if legacy.is_file():
            legacy.unlink()
            actions.append(f"removed legacy {legacy.name}")
    return actions


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


def load_prior_baseline(project_root: Path) -> tuple[str | None, str | None]:
    """Return ``(source_digest, package_version)`` from the prior manifest.

    Both ``None`` when no manifest exists or the fields predate drift
    tracking — callers treat that as "no baseline yet, don't report drift",
    so existing projects never get a spurious drift warning before their
    first redeploy under the drift-aware deployer.
    """
    path = project_root / DEPLOY_MANIFEST_REL
    if not path.is_file():
        return None, None
    try:
        data = read_json(path)
    except ConfigError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    digest = data.get("source_digest")
    version = data.get("package_version")
    return (
        digest if isinstance(digest, str) else None,
        version if isinstance(version, str) else None,
    )


def save_manifest(project_root: Path, manifest: DeployManifest) -> None:
    """Persist *manifest* to ``.cataforge/.deploy-manifest.json``.

    Written atomically: an interrupted write leaves the prior manifest
    intact rather than a truncated file that the next deploy's prune
    step cannot parse.
    """
    path = project_root / DEPLOY_MANIFEST_REL
    payload = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(path, payload)


def manifest_path(project_root: Path) -> Path:
    """Where the manifest lives. Exposed for ``--rebuild`` / doctor."""
    return project_root / DEPLOY_MANIFEST_REL
