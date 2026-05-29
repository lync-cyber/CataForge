"""Deployment algorithm mixins for :class:`PlatformAdapter`.

These mixins carry the per-resource deploy logic (agents / instructions /
skills / commands+rules / mcp). They keep ``self`` semantics so concrete
adapters can override individual deploy methods and call ``super()``; the
config/capability surface stays on :class:`~cataforge.adapter.platform.adapter.PlatformAdapter`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.adapter.platform.instruction_cache import (
    load_instruction_hashes,
    save_instruction_hashes,
)
from cataforge.adapter.platform.section_merge import merge_sections
from cataforge.core.errors import CataforgeError

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest

_VALID_ON_CONFLICT = {"overwrite", "preserve", "preserve_if_edited"}
_VALID_UPDATE_STRATEGY = {"overwrite", "section-merge"}

# Cheap frontmatter scan for ``maintainer-only: true``. Avoids importing
# SkillLoader from the platform layer (the loader pulls in builtins and
# project config, neither of which the deployer needs at this point).
_MAINTAINER_ONLY_RE = re.compile(r"^maintainer-only\s*:\s*true\s*$", re.IGNORECASE | re.MULTILINE)


def _peek_maintainer_only(skill_md: Path) -> bool:
    try:
        text = skill_md.read_text(encoding="utf-8")
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


def _dry_run_agent_lines(agent_src_dir: Path, agent_name: str, target_rel: str) -> list[str]:
    """Describe what a non-dry-run deploy of one agent dir would write.

    Shows both the logical source and the physical target so users can't
    confuse "same filename in every line" for "all agents being written to
    the same file".
    """
    lines = [f"would deploy agent {agent_name:<24} → {target_rel}/{agent_name}/AGENT.md"]
    for sibling in sorted(agent_src_dir.iterdir()):
        if sibling.is_file() and sibling.suffix == ".md" and sibling.name != "AGENT.md":
            lines.append(
                f"would deploy agent-doc {agent_name}/{sibling.name:<32} → "
                f"{target_rel}/{agent_name}/{sibling.name}"
            )
    return lines


def _dropped_capability_warnings(
    platform_id: str, dropped_collector: dict[str, set[str]]
) -> list[str]:
    """One aggregated WARN per agent-field that lost capability mappings."""
    warnings: list[str] = []
    for field_name in sorted(dropped_collector):
        caps = sorted(dropped_collector[field_name])
        warnings.append(
            f"WARN: {platform_id}: {len(caps)} capability id(s) in "
            f"{field_name!r} have no platform mapping: {caps} — "
            "these will be skipped during translation."
        )
    return warnings


class AgentDeployMixin:
    """Agent deployment (cataforge agents → platform-native agent files)."""

    def deploy_agents(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        """Deploy agent definitions to platform target directories.

        Default: translates yaml-frontmatter agent files and copies them.
        Subclasses override for different formats (e.g. TOML).
        """
        scan_dirs = self.get_agent_scan_dirs()
        if not scan_dirs:
            return []

        target_dir = project_root / scan_dirs[0]
        target_rel = scan_dirs[0]
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        actions: list[str] = []
        if not source_dir.is_dir():
            return actions

        source_agents = {
            d.name for d in source_dir.iterdir() if d.is_dir() and (d / "AGENT.md").is_file()
        }

        # Collect dropped capabilities across all agents so we emit ONE line
        # per platform instead of spamming one warning per agent per field.
        dropped_collector: dict[str, set[str]] = {}

        for agent_name in sorted(source_agents):
            agent_src_dir = source_dir / agent_name
            agent_dst = target_dir / agent_name
            if dry_run:
                actions.extend(_dry_run_agent_lines(agent_src_dir, agent_name, target_rel))
                continue
            actions.extend(
                self._write_agent_dir(
                    agent_src_dir,
                    agent_dst,
                    agent_name,
                    target_rel,
                    dropped_collector,
                    manifest,
                    prior_manifest,
                )
            )

        actions.extend(_dropped_capability_warnings(self.platform_id, dropped_collector))
        actions.extend(
            self._prune_orphan_agent_dirs(
                target_dir, source_agents, scan_dirs[0], target_rel, prior_manifest, dry_run
            )
        )
        return actions

    def _write_agent_dir(
        self,
        agent_src_dir: Path,
        agent_dst: Path,
        agent_name: str,
        target_rel: str,
        dropped_collector: dict[str, set[str]],
        manifest: DeployManifest | None,
        prior_manifest: set[str] | None,
    ) -> list[str]:
        """Render+write a single agent's AGENT.md and sibling *.md, pruning stale siblings.

        Both AGENT.md and its sibling *.md (PROTOCOLS, META, …) deploy into
        the platform's per-agent subdir. The siblings carry detailed protocol
        material that AGENT.md references; without them in the IDE-visible tree
        the LLM follows a placeholder-laden source path back into .cataforge/
        and sees unrendered tokens. Render at write time so {INSTRUCTION_FILE}
        / {AGENTS_DIR} etc. resolve to platform-native values before the file
        lands.
        """
        from cataforge.core.template import render_runtime_content
        from cataforge.runtime.agent.translator import translate_agent_md

        actions: list[str] = []
        agent_dst.mkdir(exist_ok=True)
        content = (agent_src_dir / "AGENT.md").read_text(encoding="utf-8")
        translated = translate_agent_md(content, self, dropped_collector=dropped_collector)
        rendered = render_runtime_content(translated, self)
        (agent_dst / "AGENT.md").write_text(rendered, encoding="utf-8")
        if manifest is not None:
            manifest.record(f"{target_rel}/{agent_name}/AGENT.md")
        actions.append(f"agents/{agent_name}/AGENT.md → {target_rel}")

        # Render and write sibling *.md files. Track each in the manifest so
        # the next deploy's orphan prune can reclaim stale ones the source
        # removed, without touching user-authored ones the manifest doesn't
        # know about.
        written_siblings: set[str] = set()
        for sibling in sorted(agent_src_dir.iterdir()):
            if not (sibling.is_file() and sibling.suffix == ".md"):
                continue
            if sibling.name == "AGENT.md":
                continue
            sib_rendered = render_runtime_content(sibling.read_text(encoding="utf-8"), self)
            (agent_dst / sibling.name).write_text(sib_rendered, encoding="utf-8")
            written_siblings.add(sibling.name)
            if manifest is not None:
                manifest.record(f"{target_rel}/{agent_name}/{sibling.name}")
            actions.append(f"agents/{agent_name}/{sibling.name} → {target_rel}/{agent_name}")

        # Prune sibling *.md that previous deploys wrote but source no longer
        # carries. Scope tightly: only files in prior_manifest, never AGENT.md
        # itself, never non-md files (user backups etc.).
        for existing in agent_dst.iterdir():
            if not (existing.is_file() and existing.suffix == ".md"):
                continue
            if existing.name == "AGENT.md" or existing.name in written_siblings:
                continue
            existing_rel = f"{target_rel}/{agent_name}/{existing.name}"
            if prior_manifest is not None and existing_rel not in prior_manifest:
                continue
            existing.unlink()
            actions.append(f"pruned orphan {target_rel}/{agent_name}/{existing.name}")
        return actions

    def _prune_orphan_agent_dirs(
        self,
        target_dir: Path,
        source_agents: set[str],
        scan_dir: str,
        target_rel: str,
        prior_manifest: set[str] | None,
        dry_run: bool,
    ) -> list[str]:
        """Remove agent subdirs no longer present in source.

        The subdir-with-AGENT.md ownership check stays as a defence-in-depth
        layer (we never touch dirs that don't look like ours), and on top of
        that the manifest scoping ensures we only delete agents we actually
        wrote in a prior deploy — user-authored agents that happen to follow
        our naming pattern survive.
        """
        if not target_dir.is_dir():
            return []
        from cataforge.adapter.platform.helpers import remove_dir_with_manifest_check

        actions: list[str] = []
        for existing in target_dir.iterdir():
            if (
                not existing.is_dir()
                or existing.name in source_agents
                or not (existing / "AGENT.md").is_file()
            ):
                continue
            actions.extend(
                remove_dir_with_manifest_check(
                    existing,
                    display_rel=f"{scan_dir}/{existing.name}",
                    manifest_key=f"{target_rel}/{existing.name}/AGENT.md",
                    prior_manifest=prior_manifest,
                    dry_run=dry_run,
                    kind="orphan",
                )
            )
        return actions

    def _deploy_flat_agents(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        target_rel: str,
        suffix: str,
        head_signature: str,
        formatter: Callable[[str, str], str],
        head_read_size: int = 512,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        """Shared write+prune+warn pipeline for adapters that emit
        ``<name>{suffix}`` files (Claude Code .md, Codex .toml, OpenCode .md).

        Each caller plugs in:

        * ``target_rel`` — relative target dir (``scan_dirs[0]`` for most,
          hardcoded ``.opencode/agents`` for OpenCode which doesn't expose
          this via the agent_definition profile section).
        * ``suffix`` — the file extension to write (``.md`` / ``.toml``).
        * ``formatter(agent_name, translated)`` — final-content producer.
          For identity-output adapters (ClaudeCode, OpenCode) this is
          ``lambda _name, translated: translated``; for Codex it wraps
          the translated yaml-frontmatter agent into TOML.
        * ``head_signature`` — ownership signature used by orphan prune.
          The flat-prune helper only removes files whose head bytes
          contain ``head_signature.format(stem=<file_stem>)``, so a
          user-authored file that happens to share the suffix survives.
        * ``head_read_size`` — bytes to scan for the signature (default
          512 matches the base helper; Codex's TOML header fits in 256).

        Behaviour matches what the three call sites had open-coded:

        1. Make the target dir.
        2. Enumerate source agents (subdirs with ``AGENT.md``).
        3. Translate each via :func:`translate_agent_md`, then run the
           caller's ``formatter`` and write to ``target_dir / f"{name}{suffix}"``.
        4. Record each written path in the manifest (when supplied).
        5. Prune orphan flat files via :func:`_prune_orphan_flat_files`
           with the caller's signature, bounded by ``prior_manifest`` so
           user-authored files we never wrote stay put.
        6. Emit one aggregated WARN per agent-field that lost capability
           mappings on this platform.
        """
        from cataforge.adapter.platform.helpers import _prune_orphan_flat_files
        from cataforge.core.template import render_runtime_content
        from cataforge.runtime.agent.translator import translate_agent_md

        target_dir = project_root / target_rel
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        actions: list[str] = []
        if not source_dir.is_dir():
            return actions

        source_agents = {
            d.name for d in source_dir.iterdir() if d.is_dir() and (d / "AGENT.md").is_file()
        }
        dropped_collector: dict[str, set[str]] = {}

        for agent_name in sorted(source_agents):
            agent_md = source_dir / agent_name / "AGENT.md"
            target_file = target_dir / f"{agent_name}{suffix}"
            target_rel_full = f"{target_rel}/{agent_name}{suffix}"

            if dry_run:
                actions.append(f"would deploy agent {agent_name:<24} → {target_rel_full}")
                continue

            content = agent_md.read_text(encoding="utf-8")
            translated = translate_agent_md(content, self, dropped_collector=dropped_collector)
            # Render runtime placeholders BEFORE the formatter wraps the body
            # — Codex's TOML wrapper embeds the markdown verbatim, so rendering
            # afterwards would have to re-parse the TOML to find the body.
            rendered = render_runtime_content(translated, self)
            final = formatter(agent_name, rendered)
            target_file.write_text(final, encoding="utf-8")
            if manifest is not None:
                manifest.record(target_rel_full)
            actions.append(f"agents/{agent_name}/AGENT.md → {target_rel_full}")

        actions.extend(
            _prune_orphan_flat_files(
                target_dir,
                source_agents,
                suffix,
                head_signature,
                target_rel,
                head_read_size=head_read_size,
                dry_run=dry_run,
                prior_manifest=prior_manifest,
            )
        )

        actions.extend(_dropped_capability_warnings(self.platform_id, dropped_collector))
        return actions


class InstructionDeployMixin:
    """Instruction-file deployment (CLAUDE.md / AGENTS.md + extras)."""

    def deploy_instruction_files(
        self,
        project_state_path: Path,
        project_root: Path,
        *,
        platform_id: str,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        """Deploy platform instruction artifacts derived from PROJECT-STATE.md.

        Each target entry may declare:
        - ``on_conflict``: ``overwrite`` (default) | ``preserve`` |
          ``preserve_if_edited``.  ``preserve_if_edited`` skips write when the
          target's sha256 differs from the hash recorded at last deploy.
        - ``update_strategy``: ``overwrite`` (default) | ``section-merge``.
          ``section-merge`` preserves user-added sections and field values per
          the ``section_policy`` declared on the target.
        """
        if not project_state_path.is_file():
            return ["SKIP: PROJECT-STATE.md not found"]

        from cataforge.core.template import render_project_state, render_runtime_content

        content = project_state_path.read_text(encoding="utf-8")
        content = render_project_state(content, platform_id)
        # Apply runtime placeholders ({INSTRUCTION_FILE}, {RULES_DIR}, …) so
        # the user's CLAUDE.md / AGENTS.md ships with platform-native paths
        # baked in. ``render_project_state`` only handles the legacy
        # ``运行时: {platform}`` token; this second pass picks up the new
        # placeholder surface declared by the renderer registry.
        content = render_runtime_content(content, self)

        # Prepend an at-mention preamble when the platform declares one via
        # context_injection.  Today only Claude Code uses this — CLAUDE.md gets
        # `@.cataforge/rules/COMMON-RULES.md` at the top so the shared rule
        # file rides into every session without a runtime Read call.
        preamble = self.get_instruction_preamble()
        if preamble:
            content = preamble + content

        actions: list[str] = []
        hashes = load_instruction_hashes(project_root)
        hashes_dirty = False

        for target in self.instruction_targets:
            target_type = str(target.get("type", ""))
            target_rel = str(target.get("path", ""))
            if not target_rel:
                continue
            if target_type != "project_state_copy":
                actions.append(f"SKIP: unsupported instruction target type {target_type}")
                continue

            on_conflict = str(target.get("on_conflict", "overwrite"))
            if on_conflict not in _VALID_ON_CONFLICT:
                actions.append(
                    f"SKIP {target_rel}: invalid on_conflict={on_conflict!r} "
                    f"(must be one of {sorted(_VALID_ON_CONFLICT)})"
                )
                continue

            update_strategy = str(target.get("update_strategy", "overwrite"))
            if update_strategy not in _VALID_UPDATE_STRATEGY:
                actions.append(
                    f"SKIP {target_rel}: invalid update_strategy={update_strategy!r} "
                    f"(must be one of {sorted(_VALID_UPDATE_STRATEGY)})"
                )
                continue

            dst = project_root / target_rel
            try:
                dst.resolve().relative_to(project_root.resolve())
            except ValueError as exc:
                raise CataforgeError(f"target_rel escapes project root: {target_rel!r}") from exc

            # ---- on_conflict gate ----
            if dst.exists() and on_conflict != "overwrite":
                if on_conflict == "preserve":
                    actions.append(f"SKIP {target_rel} ← on_conflict=preserve (target exists)")
                    continue
                # preserve_if_edited: compare sha256 with last-deployed hash
                cur_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
                last_hash = hashes.get(target_rel)
                if last_hash is not None and cur_hash != last_hash:
                    actions.append(
                        f"SKIP {target_rel} ← on_conflict=preserve_if_edited "
                        f"(user-edited since last deploy)"
                    )
                    continue

            # ---- compute new content ----
            new_content = content
            if update_strategy == "section-merge" and dst.exists():
                section_policy = target.get("section_policy", {}) or {}
                current_text = dst.read_text(encoding="utf-8")
                new_content = merge_sections(
                    current_text,
                    content,
                    policy=section_policy,
                    platform_id=platform_id,
                )

            if dry_run:
                actions.append(
                    f"would write {target_rel} ← PROJECT-STATE.md "
                    f"(platform={platform_id}, strategy={update_strategy}, "
                    f"on_conflict={on_conflict})"
                )
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(new_content, encoding="utf-8")
            # Hash what's actually on disk — avoids Windows CRLF translation
            # making cur_hash on subsequent deploys diverge from the stored
            # hash even when the user has not edited the file.
            hashes[target_rel] = hashlib.sha256(dst.read_bytes()).hexdigest()
            hashes_dirty = True
            if manifest is not None:
                manifest.record(target_rel)
            actions.append(
                f"{target_rel} ← PROJECT-STATE.md (platform={platform_id}, "
                f"strategy={update_strategy})"
            )

        if hashes_dirty and not dry_run:
            save_instruction_hashes(project_root, hashes)

        return actions


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
            original = md_file.read_text(encoding="utf-8")
            rendered = render_runtime_content(original, self)
            if rendered != original:
                md_file.write_text(rendered, encoding="utf-8")
        return actions


class CommandRulesDeployMixin:
    """Command and rules deployment (+ overrides rules flow)."""

    def deploy_commands(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        """Copy ``.cataforge/commands/*.md`` into the platform's slash-command dir.

        Default: flat copy of every ``*.md`` file.  Subclasses may override for
        platforms with different slash-command formats.

        Prune scope is bounded by ``prior_manifest``: we only delete
        ``*.md`` entries that the previous deploy claimed ownership of, so
        hand-authored slash commands (e.g. the git-tracked dogfood wrapper
        ``framework-issue-resolve.md``) survive every redeploy.
        """
        target_rel = self.get_command_target_dir()
        if not target_rel or not source_dir.is_dir():
            return []
        target_dir = project_root / target_rel
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        source_names = {md.name for md in source_dir.glob("*.md")}
        actions: list[str] = []

        # Prune stale commands the previous deploy wrote but that are no
        # longer in source. Without ``prior_manifest`` we fall back to the
        # legacy "anything orphaned in target" rule for direct callers that
        # pre-date the manifest plumbing — production deploy always threads
        # the manifest in, so user-authored files are protected end-to-end.
        if target_dir.is_dir():
            for existing in target_dir.glob("*.md"):
                if existing.name in source_names:
                    continue
                existing_rel = f"{target_rel}/{existing.name}"
                if prior_manifest is not None and existing_rel not in prior_manifest:
                    continue
                if dry_run:
                    actions.append(f"would prune orphan {target_rel}/{existing.name}")
                else:
                    existing.unlink()
                    actions.append(f"pruned orphan {target_rel}/{existing.name}")

        from cataforge.core.template import render_runtime_content

        for md_file in sorted(source_dir.glob("*.md")):
            dst = target_dir / md_file.name
            cmd_rel = f"{target_rel}/{md_file.name}"
            if dry_run:
                actions.append(
                    f"would deploy commands/{md_file.name} → {target_rel}/{md_file.name}"
                )
                continue
            rendered = render_runtime_content(md_file.read_text(encoding="utf-8"), self)
            dst.write_text(rendered, encoding="utf-8")
            if manifest is not None:
                manifest.record(cmd_rel)
            actions.append(f"commands/{md_file.name} → {target_rel}")
        return actions

    def deploy_rules(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
        force_copy: bool = False,
    ) -> list[str]:
        """Deploy rule files to the platform's rule directory.

        Copy + render so placeholders in ``COMMON-RULES.md`` /
        ``SUB-AGENT-PROTOCOLS.md`` reach the IDE already substituted.
        ``force_copy`` is retained for API parity with the skills path; the
        default now always copies (rendering forces independent copies —
        symlinks would point back at unrendered source).
        """
        del force_copy  # retained for API compat; always copy under J render

        scan_dirs = self.get_agent_scan_dirs()
        if not scan_dirs:
            return []
        platform_root = Path(scan_dirs[0]).parent
        target = project_root / platform_root / "rules"
        actions = self._copy_render_md_tree(source_dir, target, dry_run=dry_run)
        if manifest is not None and not dry_run:
            manifest.record(f"{platform_root.as_posix()}/rules")
        return actions

    def deploy_additional_outputs(
        self,
        rules_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        """Deploy platform-specific additional outputs.

        Default: no-op. Subclasses override (e.g. Cursor MDC rules).
        """
        return []

    def deploy_overrides_rules(
        self,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
    ) -> list[str]:
        """Materialise platform override rules into native artefacts.

        Scans ``.cataforge/platforms/{platform_id}/overrides/rules/*.md``
        (both hand-authored rules and auto-generated ones from hook bridge
        ``apply_degradation``) and writes each through
        :meth:`_wrap_rule_for_platform`.

        Subclasses control output format and target path by overriding the
        hook; the default produces a verbatim copy at
        ``<context_injection.rules_distribution.target>/<name>.md``.
        Returning ``None`` from the hook signals the platform opted not to
        emit a file (e.g. when the rule is registered through a different
        mechanism such as ``opencode.json#instructions``).
        """
        overrides_dir = (
            project_root / ".cataforge" / "platforms" / self.platform_id / "overrides" / "rules"
        )
        if not overrides_dir.is_dir():
            return []

        actions: list[str] = []
        for md_file in sorted(overrides_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            wrapped = self._wrap_rule_for_platform(md_file.stem, content)
            if wrapped is None:
                actions.append(
                    f"SKIP: overrides/rules/{md_file.name} — "
                    f"{self.platform_id} platform opted not to materialise"
                )
                continue
            target_rel, body = wrapped
            target_path = project_root / target_rel
            if dry_run:
                actions.append(f"would deploy overrides/rules/{md_file.name} → {target_rel}")
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(body, encoding="utf-8")
            if manifest is not None:
                manifest.record(target_rel)
            actions.append(f"overrides/rules/{md_file.name} → {target_rel}")
        return actions

    def _wrap_rule_for_platform(self, name: str, content: str) -> tuple[str, str] | None:
        """Return ``(target_relpath, body)`` for an override rule, or ``None``.

        Default: copy verbatim to
        ``<context_injection.rules_distribution.target>/<name>.md`` when the
        profile declares a rules target; otherwise return ``None`` (skip).

        Subclasses override to:

        * change the wrapping (e.g. Cursor wraps as MDC with ``alwaysApply``)
        * change the target path
        * return ``None`` to suppress writing entirely (e.g. when the rule
          is surfaced through a different mechanism)
        """
        rules_target = self._default_rules_target_dir()
        if not rules_target:
            return None
        return (f"{rules_target}/{name}.md", content)

    def _default_rules_target_dir(self) -> str | None:
        """Return the platform's declared rule distribution directory, if any.

        Looks at ``context_injection.rules_distribution.target`` in the
        profile.  Used by :meth:`_wrap_rule_for_platform` so subclasses that
        only want to change wrapping (not the target path) can call this
        helper instead of re-reading the profile.
        """
        target = (self.context_injection.get("rules_distribution", {}) or {}).get("target")
        return str(target) if target else None


class McpDeployMixin:
    """MCP server config injection into the platform's mcp.json."""

    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        """Write MCP server config into the platform's configuration file.

        Default: merge into a JSON file under the standard ``mcpServers.<id>``
        key via :func:`merge_json_key`.  The concrete path comes from
        :meth:`_mcp_json_path` which subclasses override.  Platforms using a
        non-JSON or non-standard layout (e.g. Codex TOML, OpenCode's per-repo
        merge) override ``inject_mcp_config`` itself instead.
        """
        from cataforge.adapter.platform.helpers import merge_json_key

        mcp_path = self._mcp_json_path(project_root)
        return merge_json_key(mcp_path, f"mcpServers.{server_id}", server_config, dry_run=dry_run)

    def _mcp_json_path(self, project_root: Path) -> Path:
        """Return the JSON file path the default ``inject_mcp_config`` writes to.

        Subclasses that rely on the default implementation override this
        single method; adapters with fully custom MCP layouts override
        ``inject_mcp_config`` directly and can leave this raising.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must override either inject_mcp_config() or _mcp_json_path()"
        )
