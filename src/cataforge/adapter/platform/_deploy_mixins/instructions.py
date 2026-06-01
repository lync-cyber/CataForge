"""Instruction-file deployment mixin (CLAUDE.md / AGENTS.md + extras)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

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

        content = project_state_path.read_text()
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
                current_text = dst.read_text()
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
            dst.write_text(new_content)
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
