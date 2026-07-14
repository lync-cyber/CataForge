"""Instruction-file deployment step (CLAUDE.md / AGENTS.md + extras)."""

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
from cataforge.core.template import render_project_state
from cataforge.runtime.deploy.template_render import render_runtime_content
from cataforge.utils.atomic_write import atomic_write_text

if TYPE_CHECKING:
    from cataforge.adapter.platform.adapter import PlatformAdapter
    from cataforge.runtime.deploy.manifest import DeployManifest

_VALID_ON_CONFLICT = {"overwrite", "preserve", "preserve_if_edited"}
_VALID_UPDATE_STRATEGY = {"overwrite", "section-merge"}


def _on_conflict_skip(
    dst: Path,
    target_rel: str,
    on_conflict: str,
    hashes: dict[str, str],
) -> str | None:
    """Return a SKIP action string if the on_conflict policy blocks writing, else None."""
    if not dst.exists() or on_conflict == "overwrite":
        return None
    if on_conflict == "preserve":
        return f"SKIP {target_rel} ← on_conflict=preserve (target exists)"
    # preserve_if_edited: skip when the file has been edited since last deploy
    cur_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
    last_hash = hashes.get(target_rel)
    if last_hash is not None and cur_hash != last_hash:
        return f"SKIP {target_rel} ← on_conflict=preserve_if_edited (user-edited since last deploy)"
    return None


def _render_target_content(
    raw_template: str,
    adapter: PlatformAdapter,
    *,
    platform_id: str,
    audience: list[str],
    design_tool: str,
    manual_review_checkpoints: list[str] | None,
) -> str:
    """Render the instruction template for one target's platform audience.

    Shared files (audience > 1) render the audience set and platform-neutral
    source paths so their bytes are independent of deploy order.
    """
    shared = len(audience) > 1
    content = render_project_state(
        raw_template,
        audience if shared else platform_id,
        design_tool=design_tool,
        manual_review_checkpoints=manual_review_checkpoints,
    )
    content = render_runtime_content(content, adapter, neutral=shared)
    preamble = adapter.get_instruction_preamble()
    if preamble:
        content = preamble + content
    return content


def deploy_instruction_files(
    adapter: PlatformAdapter,
    project_state_path: Path,
    project_root: Path,
    *,
    platform_id: str,
    design_tool: str = "none",
    manual_review_checkpoints: list[str] | None = None,
    instruction_audience: dict[str, list[str]] | None = None,
    primary_state_source: str | None = None,
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

    ``instruction_audience`` maps a target path to the full set of platforms
    whose profile writes that same file. A shared file (AGENTS.md) renders
    from the audience set with platform-neutral paths, so its bytes never
    depend on which platform deployed last.
    """
    if not project_state_path.is_file():
        return ["SKIP: PROJECT-STATE.md not found"]

    raw_template = project_state_path.read_text()

    actions: list[str] = []
    hashes = load_instruction_hashes(project_root)
    hashes_dirty = False

    for target in adapter.instruction_targets:
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
        skip_action = _on_conflict_skip(dst, target_rel, on_conflict, hashes)
        if skip_action:
            actions.append(skip_action)
            continue

        # ---- render for this target's platform audience ----
        audience = (instruction_audience or {}).get(target_rel) or [platform_id]
        content = _render_target_content(
            raw_template,
            adapter,
            platform_id=platform_id,
            audience=audience,
            design_tool=design_tool,
            manual_review_checkpoints=manual_review_checkpoints,
        )

        # ---- compute new content ----
        new_content = content
        section_policy = target.get("section_policy", {}) or {}
        if update_strategy == "section-merge" and dst.exists():
            current_text = dst.read_text()
            new_content = merge_sections(
                current_text,
                content,
                policy=section_policy,
                platform_id=platform_id,
            )
        elif update_strategy == "section-merge" and primary_state_source is not None:
            # Fresh secondary instruction file: seed its runtime sections
            # (§项目状态 / §执行环境) from the primary instruction file so a
            # newly enabled platform starts from the live project state
            # instead of template placeholders. The primary stays the SSOT;
            # doctor reports projection drift afterwards.
            primary_path = project_root / primary_state_source
            if primary_state_source != target_rel and primary_path.is_file():
                new_content = merge_sections(
                    primary_path.read_text(),
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
        atomic_write_text(dst, new_content)
        # Hash what's actually on disk — avoids Windows CRLF translation
        # making cur_hash on subsequent deploys diverge from the stored
        # hash even when the user has not edited the file.
        hashes[target_rel] = hashlib.sha256(dst.read_bytes()).hexdigest()
        hashes_dirty = True
        if manifest is not None:
            manifest.record(target_rel)
        actions.append(
            f"{target_rel} ← PROJECT-STATE.md (platform={platform_id}, strategy={update_strategy})"
        )

    if hashes_dirty and not dry_run:
        save_instruction_hashes(project_root, hashes)

    actions.extend(
        adapter.post_instruction_deploy(project_root, dry_run=dry_run, manifest=manifest)
    )
    return actions
