"""Claude Code platform adapter."""

from __future__ import annotations

from pathlib import Path

from cataforge.platform.base import PlatformAdapter


class ClaudeCodeAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

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
        implementation's ``<name>/AGENT.md`` subdir layout is not picked up
        by Claude Code's native ``/agents`` command, so we override to emit
        only the flat form.

        Orphan pruning covers flat ``.md`` files we likely wrote and any
        leftover ``<name>/AGENT.md`` subdirs from prior deploys.
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

            if dry_run:
                actions.append(
                    f"would deploy agent {agent_name:<24} "
                    f"→ {target_rel}/{agent_name}.md"
                )
                continue

            translated = translate_agent_md(
                content, self, dropped_collector=dropped_collector
            )
            flat_dst.write_text(translated, encoding="utf-8")
            actions.append(f"agents/{agent_name}/AGENT.md → {target_rel}")

        # Prune orphans. Touch only files/dirs that look like ours — flat
        # ``<name>.md`` files whose frontmatter names match our translator
        # output, and subdirs containing ``AGENT.md`` (leftover from the
        # pre-M? dual layout). IDE-native and user-authored files stay put.
        if target_dir.is_dir():
            for existing in target_dir.iterdir():
                if existing.is_dir():
                    if (existing / "AGENT.md").is_file():
                        if dry_run:
                            actions.append(
                                f"would prune legacy {target_rel}/{existing.name}/"
                            )
                        else:
                            import shutil as _shutil

                            _shutil.rmtree(existing)
                            actions.append(f"pruned legacy {target_rel}/{existing.name}/")
                    continue

                if (
                    existing.is_file()
                    and existing.suffix == ".md"
                    and existing.stem not in source_agents
                ):
                    # Defensive: only drop flat files whose frontmatter
                    # ``name:`` matches — avoids touching user-authored .md.
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

    def _mcp_json_path(self, project_root: Path) -> Path:
        return project_root / ".mcp.json"
