"""Agent deployment mixin (cataforge agents → platform-native agent files)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.utils.atomic_write import atomic_write_text

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest


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
        # Free-form WARN lines (allow/deny tool collisions, dropped
        # security-sensitive fields) surfaced alongside the action log.
        warnings_collector: list[str] = []

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
                    warnings_collector,
                    manifest,
                    prior_manifest,
                )
            )

        actions.extend(_dropped_capability_warnings(self.platform_id, dropped_collector))
        actions.extend(warnings_collector)
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
        warnings_collector: list[str],
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
        content = (agent_src_dir / "AGENT.md").read_text()
        translated = translate_agent_md(
            content,
            self,
            dropped_collector=dropped_collector,
            warnings_collector=warnings_collector,
        )
        rendered = render_runtime_content(translated, self)
        atomic_write_text(agent_dst / "AGENT.md", rendered)
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
            sib_rendered = render_runtime_content(sibling.read_text(), self)
            atomic_write_text(agent_dst / sibling.name, sib_rendered)
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
        warnings_collector: list[str] = []

        for agent_name in sorted(source_agents):
            agent_md = source_dir / agent_name / "AGENT.md"
            target_file = target_dir / f"{agent_name}{suffix}"
            target_rel_full = f"{target_rel}/{agent_name}{suffix}"

            if dry_run:
                actions.append(f"would deploy agent {agent_name:<24} → {target_rel_full}")
                continue

            content = agent_md.read_text()
            translated = translate_agent_md(
                content,
                self,
                dropped_collector=dropped_collector,
                warnings_collector=warnings_collector,
            )
            # Render runtime placeholders BEFORE the formatter wraps the body
            # — Codex's TOML wrapper embeds the markdown verbatim, so rendering
            # afterwards would have to re-parse the TOML to find the body.
            rendered = render_runtime_content(translated, self)
            final = formatter(agent_name, rendered)
            atomic_write_text(target_file, final)
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
        actions.extend(warnings_collector)
        return actions
