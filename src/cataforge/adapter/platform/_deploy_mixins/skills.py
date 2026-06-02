"""Skill-tree deployment mixin (per-skill dir → platform skill target)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest

# Cheap frontmatter scan for ``maintainer-only: true``. Avoids importing
# SkillLoader from the platform layer (the loader pulls in builtins and
# project config, neither of which the deployer needs at this point).
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


class SkillDeployMixin:
    """Skill-tree deployment (per-skill dir → platform skill target)."""

    def deploy_skills(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        include_maintainer_only: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
        force_copy: bool = False,
    ) -> list[str]:
        """Materialise each skill subdir under the IDE's skill tree via
        copy + placeholder render.

        Per-skill (not whole-dir) so the deployer can drop skills that
        declare ``maintainer-only: true`` in their SKILL.md frontmatter —
        those ship only when the caller passes ``include_maintainer_only=True``
        (``cataforge deploy --include-maintainer-only``).

        ``force_copy`` is retained for API compatibility; the new default
        always copies (and renders ``*.md`` files in the copy) because the
        symlink path served stale placeholders to the IDE. Source edits no
        longer round-trip without ``cataforge deploy``.

        ``prior_manifest`` is the ownership set from the previous deploy.
        Prune only removes target entries that *both* lack a source
        counterpart **and** appear in ``prior_manifest`` — so a user who
        hand-creates ``.claude/skills/my-skill/`` keeps it across deploys.

        Subclasses can override to transform content per platform.
        """
        del force_copy  # retained for API compat; always copy under J render
        from cataforge.adapter.platform.helpers import _is_dir_link, _remove_target

        target_rel = self.get_skill_target_dir()
        if not target_rel or not source_dir.is_dir():
            return []
        target_dir = project_root / target_rel

        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        source_names = {p.name for p in source_dir.iterdir() if p.is_dir()}
        actions: list[str] = []

        # Migrate from a pre-existing whole-dir symlink/junction left over
        # from the pre-J deploy: tear it down so we can rebuild per-skill
        # copies. ``_is_dir_link`` covers Py 3.10/3.11 junctions via ctypes.
        if _is_dir_link(target_dir):
            if dry_run:
                actions.append(f"would unwrap whole-dir link {target_rel}/")
            else:
                _remove_target(target_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                actions.append(f"unwrapped whole-dir link {target_rel}/")

        # Prune entries we previously owned but that no longer have a source.
        # ``prior_manifest is None`` → legacy caller (no manifest threaded
        # in): fall back to the old behaviour of pruning anything missing
        # from source. Tests that exercise adapters directly hit this path.
        if target_dir.is_dir():
            for existing in target_dir.iterdir():
                if existing.name in source_names:
                    continue
                existing_rel = f"{target_rel}/{existing.name}"
                if prior_manifest is not None and existing_rel not in prior_manifest:
                    # User-authored or pre-manifest legacy — leave alone.
                    continue
                if dry_run:
                    actions.append(f"would prune orphan {target_rel}/{existing.name}")
                else:
                    _remove_target(existing)
                    actions.append(f"pruned orphan {target_rel}/{existing.name}")

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
            actions.extend(self._copy_render_md_tree(skill_dir, target, dry_run=dry_run))
            if manifest is not None and not dry_run:
                manifest.record(target_rel_path)
        return actions

    def _copy_render_md_tree(
        self,
        source: Path,
        target: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        """Copy *source* tree to *target* and render ``*.md`` files in place.

        Tightly scoped helper used by :meth:`deploy_skills` and
        :meth:`deploy_rules`. Distinct from ``symlink_or_copy`` in two ways:

        1. Always copies — never symlinks/junctions. Placeholders in
           ``SKILL.md`` / ``COMMON-RULES.md`` must be substituted before the
           file reaches the IDE, which requires an independent copy.
        2. Walks the copy and rewrites every ``*.md`` file through
           :func:`render_runtime_content`, so ``{INSTRUCTION_FILE}`` and
           friends resolve to the platform-native value.

        Non-markdown files (scripts, templates with literal braces, etc.) are
        copied verbatim — the renderer is only invoked on ``*.md`` to keep
        the brace-passthrough rule from interfering with code.
        """
        import shutil

        from cataforge.adapter.platform.helpers import _remove_target
        from cataforge.core.template import render_runtime_content

        if dry_run:
            return [f"would copy+render {target} ← {source}"]

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            _remove_target(target)
        shutil.copytree(source, target)

        actions = [f"{target} ← {source} (copy+render)"]
        for md_file in target.rglob("*.md"):
            if not md_file.is_file():
                continue
            original = md_file.read_text()
            rendered = render_runtime_content(original, self)
            if rendered != original:
                md_file.write_text(rendered)
        return actions
