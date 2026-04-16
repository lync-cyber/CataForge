"""Claude Code platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.platform.base import PlatformAdapter
from cataforge.platform.helpers import merge_json_key


class ClaudeCodeAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    def get_tool_map(self) -> dict[str, str | None]:
        return dict(self._profile.get("tool_map", {}))

    def get_project_root_env_var(self) -> str | None:
        return "CLAUDE_PROJECT_DIR"

    def get_agent_scan_dirs(self) -> list[str]:
        return list(self._profile.get("agent_definition", {}).get("scan_dirs", [".claude/agents"]))

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    def deploy_agents(
        self, source_dir: Path, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Deploy agents using Claude Code's native ``<name>.md`` layout.

        Claude Code's documented sub-agent convention is a flat file per
        agent (``.claude/agents/<name>.md`` with YAML frontmatter).  The base
        implementation emits ``.claude/agents/<name>/AGENT.md``, which may
        not be picked up by Claude Code's native ``/agents`` command.

        We emit **both** layouts:

        * ``.claude/agents/<name>.md`` — the flat, IDE-native form.  This is
          what Claude Code's sub-agent discovery actually scans for.
        * ``.claude/agents/<name>/AGENT.md`` — the legacy layout retained so
          existing references (including this repo's own agents that rely on
          the subdirectory for auxiliary material) keep working.

        Orphan pruning covers both shapes.
        """
        from cataforge.agent.translator import translate_agent_md

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
            d.name
            for d in source_dir.iterdir()
            if d.is_dir() and (d / "AGENT.md").is_file()
        }

        dropped_collector: dict[str, set[str]] = {}

        for agent_name in sorted(source_agents):
            agent_md = source_dir / agent_name / "AGENT.md"
            content = agent_md.read_text(encoding="utf-8")

            flat_dst = target_dir / f"{agent_name}.md"
            dir_dst = target_dir / agent_name

            if dry_run:
                actions.append(
                    f"would deploy agent {agent_name:<24} "
                    f"→ {target_rel}/{agent_name}.md "
                    f"(also mirrored at {target_rel}/{agent_name}/AGENT.md)"
                )
                continue

            translated = translate_agent_md(
                content, self, dropped_collector=dropped_collector
            )
            flat_dst.write_text(translated, encoding="utf-8")
            dir_dst.mkdir(exist_ok=True)
            (dir_dst / "AGENT.md").write_text(translated, encoding="utf-8")
            actions.append(f"agents/{agent_name}/AGENT.md → {target_rel}")

            # Prune stale sibling files inside the agent subdir.
            for stale in dir_dst.iterdir():
                if stale.is_file() and stale.name != "AGENT.md":
                    stale.unlink()
                    actions.append(f"pruned stale {target_rel}/{agent_name}/{stale.name}")

        # Prune orphans in both layouts. Only touch files/dirs that look like
        # ours (flat .md files whose basename matches a removed agent, or
        # subdirs containing AGENT.md) so IDE-native / user-authored agents
        # living alongside stay intact.
        if target_dir.is_dir():
            for existing in target_dir.iterdir():
                if existing.is_dir():
                    if (
                        existing.name not in source_agents
                        and (existing / "AGENT.md").is_file()
                    ):
                        if dry_run:
                            actions.append(
                                f"would prune orphan {target_rel}/{existing.name}/"
                            )
                        else:
                            import shutil as _shutil

                            _shutil.rmtree(existing)
                            actions.append(f"pruned orphan {target_rel}/{existing.name}/")
                    continue

                if (
                    existing.is_file()
                    and existing.suffix == ".md"
                    and existing.stem not in source_agents
                ):
                    # Only prune flat agent files we likely wrote (those whose
                    # stem used to be a CataForge agent).  We cannot positively
                    # identify user-authored .md files, so the conservative
                    # heuristic is: if we also have a sibling <stem>/ dir that
                    # we're pruning as orphan, prune the matching flat file.
                    sibling_dir = target_dir / existing.stem
                    if sibling_dir.is_dir() or (
                        not sibling_dir.exists()
                        and existing.stem not in source_agents
                    ):
                        # Be extra defensive: only drop the flat file if the
                        # YAML frontmatter looks like one we wrote (has our
                        # translator's canonical `name:` field).
                        head = existing.read_text(encoding="utf-8", errors="ignore")[:512]
                        if f"name: {existing.stem}" in head:
                            if dry_run:
                                actions.append(
                                    f"would prune orphan {target_rel}/{existing.name}"
                                )
                            else:
                                existing.unlink()
                                actions.append(
                                    f"pruned orphan {target_rel}/{existing.name}"
                                )

        # Single aggregated WARN for unmapped capabilities — see translator.py
        # and the matching block in PlatformAdapter.deploy_agents for rationale.
        for field_name in sorted(dropped_collector):
            caps = sorted(dropped_collector[field_name])
            actions.append(
                f"WARN: {self.platform_id}: {len(caps)} capability id(s) in "
                f"{field_name!r} have no platform mapping: {caps} — "
                "these will be skipped during translation."
            )

        return actions

    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        mcp_path = project_root / ".mcp.json"
        return merge_json_key(mcp_path, f"mcpServers.{server_id}", server_config, dry_run=dry_run)
