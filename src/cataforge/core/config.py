"""Unified configuration management — single source of truth.

Fixes C-1: eliminates the `.claude/framework.json` vs `.cataforge/framework.json` split.
All config reads go through this module.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cataforge.core.io import read_json
from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.core.schema.framework import (
    FrameworkFile,
    FrameworkGitRemotePolicy,
    FrameworkGitSessionSync,
)
from cataforge.utils.atomic_write import atomic_write_text

logger = logging.getLogger("cataforge.config")


class ConfigManager:
    """Access to framework.json and derived constants.

    Primarily read-only; ``set_runtime_platform`` is the only supported
    write operation (persists ``runtime.platform`` back to disk).
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._cache: dict[str, Any] | None = None

    @property
    def paths(self) -> ProjectPaths:
        return self._paths

    # ---- framework.json ----

    def load(self) -> dict[str, Any]:
        """Load and cache the full framework.json."""
        if self._cache is not None:
            return self._cache
        path = self._paths.framework_json
        if not path.is_file():
            self._cache = {}
            return self._cache
        raw = read_json(path)
        try:
            self._cache = FrameworkFile.model_validate(raw).model_dump(
                mode="json", exclude_none=False
            )
        except ValidationError as e:
            logger.warning("framework.json validation failed, using raw JSON: %s", e)
            self._cache = raw
        return self._cache

    def load_raw(self) -> dict[str, Any]:
        """Read framework.json verbatim (no Pydantic round-trip, no caching).

        Used by write paths that must preserve exact on-disk structure and
        field order — Pydantic dumps reorder fields to schema declaration
        order and (with older schemas) dropped unknown nested keys.
        """
        path = self._paths.framework_json
        if not path.is_file():
            return {}
        data = read_json(path)
        return data if isinstance(data, dict) else {}

    def reload(self) -> dict[str, Any]:
        """Force re-read from disk."""
        self._cache = None
        return self.load()

    # ---- convenience accessors ----

    @property
    def version(self) -> str:
        """Effective scaffold version.

        The on-disk ``version`` is normally an installed package number
        stamped by ``scaffold._stamp_framework_version``. The source repo
        ships ``0.0.0-template`` as a placeholder so the committed file
        doesn't drift with each release; resolve that placeholder to the
        running package version on read so dogfood developers see a real
        number in `cataforge bootstrap` / `cataforge doctor` output.
        """
        raw = str(self.load().get("version", "0.0.0"))
        if raw.startswith("0.0.0-"):
            # Narrow to ImportError so circular-import bugs, syntax
            # errors in cataforge/__init__.py, etc. don't get silently
            # swallowed as "use the placeholder string". Only a genuine
            # missing-package situation should fall back here.
            try:
                from cataforge import __version__ as pkg_version

                return pkg_version
            except ImportError:
                return raw
        return raw

    @property
    def runtime_platform(self) -> str:
        runtime = self.load().get("runtime") or {}
        return str(runtime.get("platform", "claude-code"))

    @property
    def constants(self) -> dict[str, Any]:
        return dict(self.load().get("constants") or {})

    def get_constant(self, name: str, default: Any = None) -> Any:
        return self.constants.get(name, default)

    @property
    def features(self) -> dict[str, Any]:
        return dict(self.load().get("features") or {})

    def is_feature_enabled(self, feature_id: str) -> bool:
        feat = self.features.get(feature_id)
        if feat is None:
            return False
        return bool(feat.get("auto_enable", False))

    @property
    def upgrade_source(self) -> dict[str, Any]:
        upgrade = self.load().get("upgrade") or {}
        return dict(upgrade.get("source") or {})

    @property
    def languages(self) -> list[str]:
        """Declared ``project.languages`` (verbatim; empty list when unset).

        The canonical resolution — declaration with detection fallback and
        alias normalisation — lives in
        :func:`cataforge.core.languages.active_languages`; this accessor is the
        raw read.
        """
        project = self.load().get("project") or {}
        langs = project.get("languages")
        return [str(x) for x in langs] if isinstance(langs, list) else []

    @property
    def design_tool(self) -> str:
        """Declared ``project.design_tool`` (``none`` | ``penpot``)."""
        project = self.load().get("project") or {}
        return str(project.get("design_tool") or "none")

    # ---- git config ----

    @property
    def git_session_sync(self) -> FrameworkGitSessionSync:
        """Return the validated ``git.session_sync`` block (defaults when unset)."""
        git = self.load().get("git") or {}
        return FrameworkGitSessionSync.model_validate(git.get("session_sync") or {})

    @property
    def git_remote_policy(self) -> FrameworkGitRemotePolicy:
        """Return the validated ``git.remote_policy`` block (defaults when unset)."""
        git = self.load().get("git") or {}
        return FrameworkGitRemotePolicy.model_validate(git.get("remote_policy") or {})

    # ---- feedback / hygiene config ----

    @property
    def feedback_config(self) -> dict[str, Any]:
        return dict(self.load().get("feedback") or {})

    def feedback_gh_labels(self, kind: str) -> list[str]:
        """Return the configured ``gh issue create --label`` list for a feedback kind.

        ``kind`` ∈ {"bug", "suggest", "correction-export"}. Empty list means
        "do not pass --label" — useful when the upstream repo has no
        feedback-specific labels yet.
        """
        cfg = self.feedback_config.get("gh") or {}
        labels = (cfg.get("labels") or {}).get(kind)
        if labels is None:
            return []
        if isinstance(labels, str):
            return [labels] if labels else []
        return [str(item) for item in labels if str(item).strip()]

    def feedback_fallback_on_missing_label(self) -> bool:
        """Whether ``cataforge feedback --gh`` should retry without --label
        when ``gh issue create`` rejects an unknown label.

        Default true — keeps the user's first ``--gh`` shot from failing
        outright when the upstream repo hasn't created the labels yet.
        """
        cfg = self.feedback_config.get("gh") or {}
        return bool(cfg.get("fallback_on_missing_label", True))

    @property
    def claude_md_limits(self) -> dict[str, int]:
        """Return the CLAUDE.md hygiene thresholds.

        Defaults match framework.json defaults (30 KB / 80 state lines /
        10 learnings entries) so projects pinned to old framework.json
        without this block still get sensible doctor warnings.
        """
        defaults = {
            "max_bytes": 30000,
            "max_state_section_lines": 80,
            "learnings_registry_max_entries": 10,
            "max_state_bullet_chars": 250,
        }
        cfg = self.load().get("claude_md_limits") or {}
        result: dict[str, int] = {}
        for k, v in cfg.items():
            if isinstance(v, int | str):
                try:
                    result[k] = int(v)
                except ValueError as e:
                    raise ValueError(f"claude_md_limits.{k}: expected int, got {v!r}") from e
        return {**defaults, **result}

    # ---- save helpers ----

    def set_runtime_platform(self, platform_id: str) -> None:
        """Update ``runtime.platform`` in framework.json, preserving all other fields.

        Reads from disk verbatim (no Pydantic round-trip), patches only the
        single nested key, and writes back. Field order of every other key —
        including ``upgrade.source`` / ``upgrade.state`` subtrees and any
        user-added top-level keys — is preserved byte-for-byte except where
        the patch actually lands.
        """
        raw = self.load_raw()
        raw.setdefault("runtime", {})["platform"] = platform_id
        self._write_raw(raw)
        # Invalidate the Pydantic-view cache so the next `load()` re-reads.
        self._cache = None

    def set_languages(self, languages: list[str]) -> None:
        """Write ``project.languages``, preserving every other field.

        Same verbatim-read / single-key-patch / atomic-write discipline as
        :meth:`set_runtime_platform`, so unrelated keys keep their order.
        """
        raw = self.load_raw()
        raw.setdefault("project", {})["languages"] = list(languages)
        self._write_raw(raw)
        self._cache = None

    def set_design_tool(self, design_tool: str) -> None:
        """Write ``project.design_tool``, preserving every other field.

        Same verbatim-read / single-key-patch / atomic-write discipline as
        :meth:`set_runtime_platform`, so unrelated keys keep their order.
        """
        raw = self.load_raw()
        raw.setdefault("project", {})["design_tool"] = design_tool
        self._write_raw(raw)
        self._cache = None

    def set_context_mode(self, mode: str) -> None:
        """Write ``context.mode``, preserving every other field.

        Same verbatim-read / single-key-patch / atomic-write discipline as
        :meth:`set_runtime_platform`, so unrelated keys keep their order.
        """
        raw = self.load_raw()
        raw.setdefault("context", {})["mode"] = mode
        self._write_raw(raw)
        self._cache = None

    def describe_platform_change(self, platform_id: str) -> dict[str, Any] | None:
        """Return a description of what ``set_runtime_platform`` would change.

        Returns ``None`` when the file would remain unchanged (platform already
        matches). Otherwise returns ``{"field": "runtime.platform",
        "before": <old>, "after": <new>}`` — suitable for ``--dry-run`` /
        ``--show-diff`` display.
        """
        raw = self.load_raw()
        current = (raw.get("runtime") or {}).get("platform")
        if current == platform_id:
            return None
        return {"field": "runtime.platform", "before": current, "after": platform_id}

    def _write_raw(self, data: dict[str, Any]) -> None:
        """Write *data* to framework.json as-is (preserves key order).

        Atomic so a crash between truncate and write can't strand
        framework.json half-rewritten — which would brick every
        subsequent CLI invocation that needs the version / runtime keys.
        """
        atomic_write_text(
            self._paths.framework_json,
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        )
