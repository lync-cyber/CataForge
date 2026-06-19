"""Skill-tree deployment step (per-skill dir → platform skill target)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.adapter.platform.fileops import _is_dir_link, _remove_target, deploy_copy_ignore
from cataforge.runtime.deploy.template_render import render_runtime_content
from cataforge.utils.atomic_write import atomic_write_text

if TYPE_CHECKING:
    from cataforge.adapter.platform.adapter import PlatformAdapter
    from cataforge.runtime.deploy.manifest import DeployManifest

# Cheap frontmatter scan for ``maintainer-only: true``. Avoids importing
# SkillLoader (the loader pulls in builtins and project config, neither of
# which the deployer needs at this point).
_MAINTAINER_ONLY_RE = re.compile(r"^maintainer-only\s*:\s*true\s*$", re.IGNORECASE | re.MULTILINE)


def _peek_maintainer_only(skill_md: Path) -> bool:
    try:
        text = skill_md.read_text()
    except (OSError, UnicodeDecodeError):
        return False
    # Frontmatter ends at the second `---` line. Anything past that is body
    # — a casual mention of the phrase in the body should not be treated as
    # the directive.
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    fm = parts[1]
    return bool(_MAINTAINER_ONLY_RE.search(fm))


def _unwrap_legacy_link(target_dir: Path, target_rel: str, dry_run: bool) -> list[str]:
    """Tear down a pre-existing whole-dir symlink/junction so per-skill copies
    can be rebuilt. ``_is_dir_link`` covers Py 3.10/3.11 junctions via ctypes."""
    if not _is_dir_link(target_dir):
        return []
    if dry_run:
        return [f"would unwrap whole-dir link {target_rel}/"]
    _remove_target(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    return [f"unwrapped whole-dir link {target_rel}/"]


def _prune_orphan_skills(
    target_dir: Path,
    target_rel: str,
    source_names: set[str],
    prior_manifest: set[str] | None,
    dry_run: bool,
) -> list[str]:
    """Prune target entries we previously owned but that no longer have a source.

    ``prior_manifest is None`` → legacy caller (no manifest threaded in): fall
    back to pruning anything missing from source. Otherwise a target entry is
    pruned only when it also appears in ``prior_manifest`` — user-authored or
    pre-manifest legacy dirs are left alone.
    """
    actions: list[str] = []
    if not target_dir.is_dir():
        return actions
    for existing in target_dir.iterdir():
        if existing.name in source_names:
            continue
        existing_rel = f"{target_rel}/{existing.name}"
        if prior_manifest is not None and existing_rel not in prior_manifest:
            continue
        if dry_run:
            actions.append(f"would prune orphan {target_rel}/{existing.name}")
        else:
            _remove_target(existing)
            actions.append(f"pruned orphan {target_rel}/{existing.name}")
    return actions


def deploy_skills(
    adapter: PlatformAdapter,
    source_dir: Path,
    project_root: Path,
    *,
    dry_run: bool = False,
    include_maintainer_only: bool = False,
    manifest: DeployManifest | None = None,
    prior_manifest: set[str] | None = None,
    force_copy: bool = False,
) -> list[str]:
    """Materialise each skill subdir under the IDE's skill tree via copy + render.

    Per-skill (not whole-dir) so the deployer can drop skills that declare
    ``maintainer-only: true`` in their SKILL.md frontmatter — those ship only
    when the caller passes ``include_maintainer_only=True``
    (``cataforge deploy --include-maintainer-only``).

    Always copies (and renders ``*.md`` files in the copy); a symlink would
    serve stale placeholders to the IDE. ``force_copy`` is accepted for API
    parity but no longer changes behaviour.

    ``prior_manifest`` is the ownership set from the previous deploy. Prune
    only removes target entries that *both* lack a source counterpart **and**
    appear in ``prior_manifest`` — so a user who hand-creates
    ``.claude/skills/my-skill/`` keeps it across deploys.
    """
    del force_copy  # retained for API compat; always copy under render path

    target_rel = adapter.get_skill_target_dir()
    if not target_rel or not source_dir.is_dir():
        return []
    target_dir = project_root / target_rel

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    source_names = {p.name for p in source_dir.iterdir() if p.is_dir()}
    actions: list[str] = []
    actions.extend(_unwrap_legacy_link(target_dir, target_rel, dry_run))
    actions.extend(
        _prune_orphan_skills(target_dir, target_rel, source_names, prior_manifest, dry_run)
    )

    for skill_dir in sorted(source_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        if _peek_maintainer_only(skill_md) and not include_maintainer_only:
            actions.append(f"SKIP: {target_rel}/{skill_dir.name} (maintainer-only)")
            continue
        target = target_dir / skill_dir.name
        target_rel_path = f"{target_rel}/{skill_dir.name}"
        actions.extend(copy_render_md_tree(adapter, skill_dir, target, dry_run=dry_run))
        if manifest is not None and not dry_run:
            manifest.record(target_rel_path)
    return actions


def copy_render_md_tree(
    adapter: PlatformAdapter,
    source: Path,
    target: Path,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Copy *source* tree to *target* and render ``*.md`` files in place.

    Distinct from ``symlink_or_copy`` in two ways:

    1. Always copies — never symlinks/junctions. Placeholders in
       ``SKILL.md`` / ``COMMON-RULES.md`` must be substituted before the
       file reaches the IDE, which requires an independent copy.
    2. Walks the copy and rewrites every ``*.md`` file through
       :func:`render_runtime_content`, so ``{INSTRUCTION_FILE}`` and friends
       resolve to the platform-native value.

    Non-markdown files (scripts, templates with literal braces, etc.) are
    copied verbatim — the renderer is only invoked on ``*.md`` to keep the
    brace-passthrough rule from interfering with code.
    """
    import shutil

    if dry_run:
        return [f"would copy+render {target} ← {source}"]

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        _remove_target(target)
    shutil.copytree(source, target, ignore=deploy_copy_ignore())

    actions = [f"{target} ← {source} (copy+render)"]
    for md_file in target.rglob("*.md"):
        if not md_file.is_file():
            continue
        original = md_file.read_text()
        rendered = render_runtime_content(original, adapter)
        if rendered != original:
            atomic_write_text(md_file, rendered)
    return actions
