"""Copy the bundled ``.cataforge/`` scaffold into a user project.

The scaffold lives under :mod:`cataforge._dot_cataforge` — the canonical
repo-root ``.cataforge/`` directory packaged into the wheel via the
``[tool.hatch.build.targets.wheel.force-include]`` mapping in
``pyproject.toml``. There is no maintained mirror; ``.cataforge/`` is the
single source of truth.

Access goes through :func:`importlib.resources.files` so it works whether the
package is installed from a wheel, editable install, or running from source.
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.retired_assets import retired_skill_dirs
from cataforge.core.scaffold_backup import (
    BACKUPS_DIRNAME,
    MANIFEST_REL,
    MANIFEST_VERSION,
    _is_user_modified,
    _sha256,
    _write_manifest,
    create_backup,
    list_backups,
    read_manifest,
    restore_backup,
)

try:
    from importlib.resources.abc import Traversable
except ImportError:  # Python 3.10 — `importlib.resources.abc` landed in 3.11.
    from importlib.abc import Traversable

# ``_RUNTIME_VERSION`` is deliberately named — it reads as "the runtime
# package version" at every call site, not as a constant.
from cataforge import __version__ as _RUNTIME_VERSION  # noqa: N812

logger = logging.getLogger("cataforge.scaffold")

_PKG = "cataforge"
_SCAFFOLD_SUBDIR = "_dot_cataforge"

# Suffix for the framework copy written *beside* a user-modified scaffold file
# during a forced refresh. Rather than overwrite local edits (recoverable only
# by rolling the whole snapshot back), the new version lands at
# ``<file><SIDECAR_SUFFIX>`` for the user to diff and merge by hand.
SIDECAR_SUFFIX = ".cataforge-new"

# Re-export constants that callers (tests, upgrade_cmd) import from this module.
__all__ = [
    "BACKUPS_DIRNAME",
    "MANIFEST_REL",
    "MANIFEST_VERSION",
    "SIDECAR_SUFFIX",
    "ScaffoldCopyResult",
    "classify_scaffold_files",
    "copy_scaffold_to",
    "create_backup",
    "format_protected_warning",
    "iter_scaffold_files",
    "list_backups",
    "packaged_instruction_template",
    "read_manifest",
    "restore_backup",
]


def _stamp_framework_version(raw_bytes: bytes) -> bytes:
    """Overwrite the bundled ``framework.json`` ``version`` with the runtime.

    The bundled scaffold ships with a placeholder ``version`` value that can
    drift from the installed package (e.g. scaffold says ``0.1.0`` while the
    wheel is at ``0.1.1``).  That drift causes ``cataforge upgrade check`` to
    report "differs" forever, even directly after ``upgrade apply``.
    Stamping the runtime package version onto every write makes the package
    the single source of truth for the scaffold ``version`` field.
    """
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw_bytes
    if not isinstance(data, dict):
        return raw_bytes
    data["version"] = _RUNTIME_VERSION
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _scaffold_root() -> Traversable:
    """Resolve the bundled scaffold root.

    Wheel install: ``cataforge/_dot_cataforge/`` is materialized via the
    ``[tool.hatch.build.targets.wheel.force-include]`` mapping in
    pyproject.toml.

    Editable install (``pip install -e .``): force-include doesn't apply,
    so the in-tree package directory has no ``_dot_cataforge/`` child.
    Fall back to the repo-root ``.cataforge/`` four levels up
    (``src/cataforge/core/scaffold.py`` → ``src/cataforge/core/`` →
    ``src/cataforge/`` → ``src/`` → repo root). When that exists we
    return its ``Traversable`` view via ``files(...)`` over a fresh
    package handle; when it doesn't either path branch exists, we raise
    the same FileNotFoundError downstream code already handles.
    """
    packaged = files(_PKG).joinpath(_SCAFFOLD_SUBDIR)
    # ``Traversable`` doesn't expose ``exists()`` portably across 3.10/3.11+,
    # but ``is_dir()`` is on the protocol and answers the same question.
    if packaged.is_dir():
        return packaged
    # Editable / source-checkout fallback. Path(__file__) is the only
    # reliable anchor since the editable install's pth file may put us
    # anywhere on the user's disk.
    repo_dot_cataforge = Path(__file__).resolve().parents[3] / ".cataforge"
    if repo_dot_cataforge.is_dir():
        return repo_dot_cataforge  # Path implements Traversable in 3.11+
    return packaged  # let downstream FileNotFoundError surface naturally


# Files written into ``<project>/.cataforge/`` at deploy/upgrade time, not
# part of the scaffold. The editable-install fallback walks the live repo-root
# ``.cataforge/`` (the framework dogfoods itself), which carries these files
# from local deploys. Without this filter every scaffolded test project
# inherits the framework's own deploy state and bootstrap reports
# "deploy skip — already deployed" on a fresh fixture.
_SCAFFOLD_LOCAL_STATE_FILES: frozenset[str] = frozenset(
    {
        ".deploy-state",
        ".deploy-manifest.json",
        ".instruction-hashes.json",
        ".scaffold-manifest.json",
    }
)
# Top-level dirs holding framework-managed runtime/local state — written per
# deploy/upgrade or by a subsystem, never framework scaffold. The
# editable-install fallback walks the live repo-root ``.cataforge/`` (which
# dogfoods these) and a dirty wheel build can pack them; either way they must
# not classify as scaffold and surface as new/drift in every downstream
# project. ``kg`` is the per-project KG RocksDB store, ``.mcp-state`` the MCP
# runtime cache, ``.backups`` the upgrade rollback snapshots.
_SCAFFOLD_LOCAL_STATE_DIRS: frozenset[str] = frozenset(
    {
        ".backups",
        ".mcp-state",
        "kg",
    }
)
# Override layers are upgrade-immune, project-local customisation — never part
# of the scaffold. Bundling them would put them in the manifest and let
# ``upgrade apply`` clobber the very customisations they exist to protect.
_SCAFFOLD_OVERRIDE_DIRS: frozenset[str] = frozenset({"overrides"})
# Bundled files that are NOT copied into downstream projects. PROJECT-STATE.md
# is the source template for the platform instruction file (CLAUDE.md /
# AGENTS.md) — deploy reads it from the package, so copying it into the project
# would duplicate workflow state into a second file beside the instruction one.
_SCAFFOLD_EXCLUDED_FILES: frozenset[str] = frozenset({"PROJECT-STATE.md"})


def iter_scaffold_files() -> Iterator[tuple[str, Traversable]]:
    """Yield ``(relative_posix_path, traversable)`` for every bundled file.

    Local per-deployment state (see ``_SCAFFOLD_LOCAL_STATE_FILES`` /
    ``_SCAFFOLD_LOCAL_STATE_DIRS``) is omitted so the editable-install
    fallback does not pollute scaffolded projects with the framework's
    own deploy state.
    """

    def walk(node: Traversable, prefix: str) -> Iterator[tuple[str, Traversable]]:
        for child in node.iterdir():
            rel = f"{prefix}{child.name}"
            if child.is_dir():
                # Python bytecode cache can appear at any depth (the scaffold
                # ships ``.py`` helpers) — never part of the source surface.
                if child.name == "__pycache__":
                    continue
                if not prefix and (
                    child.name in _SCAFFOLD_LOCAL_STATE_DIRS
                    or child.name in _SCAFFOLD_OVERRIDE_DIRS
                ):
                    continue
                yield from walk(child, rel + "/")
            else:
                if not prefix and child.name in _SCAFFOLD_LOCAL_STATE_FILES:
                    continue
                if not prefix and child.name in _SCAFFOLD_EXCLUDED_FILES:
                    continue
                yield rel, child

    yield from walk(_scaffold_root(), "")


def packaged_instruction_template() -> Traversable:
    """The bundled PROJECT-STATE.md template.

    Deploy's source for generating the platform instruction file
    (CLAUDE.md / AGENTS.md). Lives in the package only — it is excluded from
    the downstream scaffold (:data:`_SCAFFOLD_EXCLUDED_FILES`), so deploy reads
    it from the package on each run rather than from the project tree.
    """
    return _scaffold_root().joinpath("PROJECT-STATE.md")


# ---- merge strategies for user-writable scaffold files ----
#
# ``--force-scaffold`` must refresh framework config without clobbering the
# parts users are expected to edit (runtime.platform picked at setup time,
# upgrade.state maintained across upgrades). Files listed here receive a
# custom merge instead of a blind overwrite.

MergeFn = Callable[[bytes, Path], bytes]


def _merge_framework_json(new_bytes: bytes, target: Path) -> bytes:
    """Overwrite scaffold-owned keys while preserving user-owned state."""
    try:
        existing = read_json(target)
    except ConfigError:
        return new_bytes

    merged: dict[str, Any] = json.loads(new_bytes.decode("utf-8"))

    # Runtime package version is injected by _stamp_framework_version already;
    # keep it so the refreshed scaffold matches the installed package.
    merged["version"] = _RUNTIME_VERSION

    # runtime.platform is chosen by the user at setup time.
    existing_runtime = existing.get("runtime") or {}
    if isinstance(existing_runtime, dict) and "platform" in existing_runtime:
        merged.setdefault("runtime", {})["platform"] = existing_runtime["platform"]

    # upgrade.state is local-only and tracks the last applied upgrade.
    existing_upgrade = existing.get("upgrade") or {}
    if isinstance(existing_upgrade, dict) and "state" in existing_upgrade:
        merged.setdefault("upgrade", {})["state"] = existing_upgrade["state"]

    # The context block holds per-project routing config — kg_active_doc_types
    # (rolling-cutover toggle), kg_definition_authority (additive authority
    # extension), strategy, authoring. All are user-owned, so existing keys win
    # over the scaffold default while still introducing any new scaffold keys.
    existing_ctx = existing.get("context")
    if isinstance(existing_ctx, dict):
        scaffold_ctx = merged.get("context")
        merged["context"] = {
            **(scaffold_ctx if isinstance(scaffold_ctx, dict) else {}),
            **existing_ctx,
        }

    # The project block is per-project user state (languages, design_tool) — an
    # upgrade must not reset it, so existing keys win over the scaffold default
    # while new scaffold keys are still introduced.
    existing_project = existing.get("project")
    if isinstance(existing_project, dict):
        scaffold_project = merged.get("project")
        merged["project"] = {
            **(scaffold_project if isinstance(scaffold_project, dict) else {}),
            **existing_project,
        }

    return (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


_MERGE_HANDLERS: dict[str, MergeFn] = {
    "framework.json": _merge_framework_json,
}


@dataclass(frozen=True)
class ScaffoldCopyResult:
    """Outcome of one :func:`copy_scaffold_to` run.

    * ``written``   — files freshly written (new copy or refreshed update).
    * ``skipped``   — existing files left untouched in a non-force copy.
    * ``protected`` — user-modified/drift files preserved during a forced
      refresh; the framework version was written beside each as
      ``<file>`` + :data:`SIDECAR_SUFFIX` for manual merge.
    * ``removed``   — obsolete manifest-recorded files pruned during a forced
      refresh (absent from the current bundle, unmodified on disk).
    * ``backup``    — pre-refresh snapshot dir, or ``None``.
    """

    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    protected: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    backup: Path | None = None


def copy_scaffold_to(
    dest: Path,
    *,
    force: bool = False,
    backup: bool = True,
) -> ScaffoldCopyResult:
    """Copy the bundled scaffold into *dest* (typically ``<project>/.cataforge``).

    Returns a :class:`ScaffoldCopyResult`. ``backup`` is the snapshot created
    before a forced refresh (or ``None`` when there was nothing to snapshot,
    or when *backup* was suppressed).

    When *force* is ``True`` existing files are refreshed, with two
    exceptions that never lose local work:

    * files registered in :data:`_MERGE_HANDLERS` receive a field-level merge
      that preserves user-owned state (e.g. ``framework.json.runtime.platform``);
    * files the user has edited away from the recorded manifest hash
      (``user-modified``/``drift``) are *kept on disk*, and the incoming
      framework version is written beside them at ``<file>`` +
      :data:`SIDECAR_SUFFIX` so the user can diff and merge by hand.

    Set *backup* to ``False`` to skip the automatic snapshot — callers doing a
    fresh install or their own backup should pass ``backup=False``.

    On every invocation, also writes ``<dest>/.scaffold-manifest.json``
    recording the bytes-hash of each written file and the package version
    that produced it, so later upgrades can classify per-file drift.
    """
    backup_path: Path | None = None
    if force and backup and dest.is_dir():
        backup_path = create_backup(dest)

    prior_manifest = read_manifest(dest)
    written: list[Path] = []
    skipped: list[Path] = []
    protected: list[Path] = []
    manifest_files: dict[str, str] = {}
    for rel, src in iter_scaffold_files():
        target = dest / rel
        exists = target.exists()

        if exists and not force:
            skipped.append(target)
            if target.is_file():
                with contextlib.suppress(OSError):
                    manifest_files[rel] = _sha256(target.read_bytes())
            continue

        with as_file(src) as src_path:
            new_bytes = Path(src_path).read_bytes()

        # Stamp the runtime package version onto framework.json for every
        # write (fresh copy or force-refresh) — keeps the scaffold version
        # aligned with the installed package without a template engine.
        if rel == "framework.json":
            new_bytes = _stamp_framework_version(new_bytes)

        if exists and force:
            handler = _MERGE_HANDLERS.get(rel)
            if handler is not None:
                new_bytes = handler(new_bytes, target)
            elif _is_user_modified(target, new_bytes, prior_manifest.get(rel)):
                # Keep the user's file; drop the framework version beside it.
                sidecar = target.with_name(target.name + SIDECAR_SUFFIX)
                sidecar.parent.mkdir(parents=True, exist_ok=True)
                sidecar.write_bytes(new_bytes)
                protected.append(target)
                # Carry the recorded hash forward unchanged; never seed one for
                # a drift file (no prior entry) — leaving it absent keeps the
                # file classifying as user-modified/drift, so the next refresh
                # protects it again instead of mistaking it for a clean update.
                if rel in prior_manifest:
                    manifest_files[rel] = prior_manifest[rel]
                continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(new_bytes)
        manifest_files[rel] = _sha256(new_bytes)
        written.append(target)

    removed: list[Path] = []
    if force:
        removed = _prune_obsolete_files(dest, prior_manifest, manifest_files, protected)
        removed += _prune_retired_skills(dest)

    _write_manifest(dest, manifest_files)
    return ScaffoldCopyResult(written, skipped, protected, removed, backup_path)


def _prune_retired_skills(dest: Path) -> list[Path]:
    """Remove framework skill source dirs retired from the scaffold.

    The manifest-scoped prune misses these when they were never tracked or were
    edited (held back as ``protected``). They are framework leftovers — project
    and user overrides live under ``.cataforge/overrides/`` — so a forced
    refresh removes the whole ``skills/<id>/`` tree. The pre-refresh backup
    makes it recoverable.
    """
    removed: list[Path] = []
    for stale in retired_skill_dirs(dest / "skills"):
        with contextlib.suppress(OSError):
            shutil.rmtree(stale)
            removed.append(stale)
    return removed


def _prune_obsolete_files(
    dest: Path,
    prior_manifest: dict[str, str],
    manifest_files: dict[str, str],
    protected: list[Path],
) -> list[Path]:
    """Delete manifest-recorded files the current bundle no longer ships.

    Only files whose on-disk bytes still match the recorded hash are removed
    — anything the user edited is kept (and reported via *protected*).
    Emptied parent directories are pruned up to *dest*.
    """
    removed: list[Path] = []
    for rel, recorded_hash in prior_manifest.items():
        if rel in manifest_files:
            continue
        target = dest / rel
        if not target.is_file():
            continue
        try:
            disk_hash = _sha256(target.read_bytes())
        except OSError:
            continue
        if disk_hash != recorded_hash:
            protected.append(target)
            continue
        with contextlib.suppress(OSError):
            target.unlink()
            removed.append(target)
            parent = target.parent
            while parent != dest and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    return removed


def format_protected_warning(protected: list[Path], dest: Path) -> list[str]:
    """Warning lines (UI-agnostic) for files preserved during a forced refresh.

    Empty when nothing was protected, so callers can ``for line in ...`` with
    no special-casing.
    """
    if not protected:
        return []
    lines = [
        f"preserved {len(protected)} user-modified file(s); the framework "
        f"version was written alongside as *{SIDECAR_SUFFIX} — review and merge:"
    ]
    for target in protected:
        rel = target.relative_to(dest) if target.is_relative_to(dest) else target
        lines.append(f"  {rel}{SIDECAR_SUFFIX}")
    return lines


def classify_scaffold_files(
    dest: Path,
) -> list[tuple[str, str]]:
    """Classify every bundled scaffold file against its *dest* counterpart.

    Returns ``(rel, status)`` tuples where ``status`` is one of:

    * ``new``                  — target does not exist on disk.
    * ``unchanged``            — target bytes already match the bundled scaffold.
    * ``update``               — target bytes match the recorded manifest hash
      (clean prior install) and differ from the bundled scaffold.
    * ``user-modified``        — target bytes differ from both manifest and
      bundled scaffold; ``--force-scaffold`` will overwrite the user edits.
    * ``preserved``            — file is in :data:`_MERGE_HANDLERS`; refresh
      performs a field-level merge instead of a blind overwrite.
    * ``drift``                — no manifest entry and target differs from
      bundled scaffold (legacy projects scaffolded pre-manifest).
    """
    manifest = read_manifest(dest)
    results: list[tuple[str, str]] = []
    for rel, src in iter_scaffold_files():
        target = dest / rel
        with as_file(src) as src_path:
            new_bytes = Path(src_path).read_bytes()
        if rel == "framework.json":
            new_bytes = _stamp_framework_version(new_bytes)
        new_hash = _sha256(new_bytes)

        if not target.exists():
            results.append((rel, "new"))
            continue

        if rel in _MERGE_HANDLERS:
            results.append((rel, "preserved"))
            continue

        try:
            disk_hash = _sha256(target.read_bytes())
        except OSError:
            results.append((rel, "user-modified"))
            continue

        if disk_hash == new_hash:
            results.append((rel, "unchanged"))
            continue

        manifest_hash = manifest.get(rel)
        if manifest_hash is None:
            results.append((rel, "drift"))
        elif disk_hash == manifest_hash:
            results.append((rel, "update"))
        else:
            results.append((rel, "user-modified"))
    return results
