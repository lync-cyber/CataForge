"""Unified configuration management — single source of truth.

Fixes C-1: eliminates the `.claude/framework.json` vs `.cataforge/framework.json` split.
All config reads go through this module.
"""

from __future__ import annotations

import json
import logging
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.core.schema.framework import (
    FrameworkFile,
    FrameworkGitRemotePolicy,
    FrameworkGitSessionSync,
)
from cataforge.utils.atomic_write import atomic_write_text

logger = logging.getLogger("cataforge.config")

# Code-level defaults surfaced by ``explain`` so "where does this value come
# from" has an answer even for fields the file never declares.
_CODE_DEFAULTS: dict[str, Any] = {
    "deployment.default_platform": "claude-code",
    "context.mode": "graph",
    "project.design_tool": "none",
}


def _dig(data: dict[str, Any], dotted_path: str) -> Any:
    """Resolve a dotted path in nested dicts; ``None`` when any hop misses."""
    node: Any = data
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class ConfigManager:
    """Access to framework.json and derived constants.

    Primarily read-only; the ``set_*`` helpers are the supported write
    operations (single-key patches under the project config lock).
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._cache: dict[str, Any] | None = None
        self._local_cache: dict[str, Any] | None = None

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

    # ---- deployment / platform resolution ----

    def load_local(self) -> dict[str, Any]:
        """Load and cache ``.cataforge/config.local.json`` (machine-local
        whitelist overlay, gitignored). Empty dict when absent/unreadable."""
        if self._local_cache is not None:
            return self._local_cache
        path = self._paths.config_local_json
        if not path.is_file():
            self._local_cache = {}
            return self._local_cache
        try:
            data = read_json(path)
        except ConfigError:
            logger.warning("config.local.json unreadable; ignoring overlay")
            data = {}
        self._local_cache = data if isinstance(data, dict) else {}
        return self._local_cache

    def explain(self, dotted_path: str) -> tuple[Any, str]:
        """Resolve *dotted_path* across layers; returns ``(value, source)``.

        Source ∈ ``env`` (explicit CATAFORGE_PLATFORM, platform paths only)
        > ``local`` (config.local.json) > ``framework`` (framework.json)
        > ``legacy`` (v1 runtime.platform fallback) > ``default``.
        """
        import os

        from cataforge.core.platform_id import FALLBACK_PLATFORM

        if dotted_path == "deployment.default_platform":
            env = os.environ.get("CATAFORGE_PLATFORM")
            if env:
                return env, "env"
        local = _dig(self.load_local(), dotted_path)
        if local is not None:
            return local, "local"
        value = _dig(self.load(), dotted_path)
        if dotted_path == "deployment.targets" and value == []:
            # An empty targets list is "undeclared", not "zero platforms" —
            # fall through to the single-default resolution below.
            value = None
        if value is not None:
            return value, "framework"
        if dotted_path == "deployment.default_platform":
            legacy = (self.load().get("runtime") or {}).get("platform")
            if legacy:
                return str(legacy), "legacy"
            return FALLBACK_PLATFORM, "default"
        if dotted_path == "deployment.targets":
            platform, source = self.explain("deployment.default_platform")
            return [platform], source if source != "framework" else "default"
        default = _CODE_DEFAULTS.get(dotted_path)
        return default, "default" if default is not None else "unset"

    @property
    def default_platform(self) -> str:
        """Resolved default platform (env > local > v2 > v1 legacy > fallback)."""
        value, _ = self.explain("deployment.default_platform")
        return str(value)

    @property
    def deployment_targets(self) -> list[str]:
        """Declared enabled-platform set; single default when undeclared."""
        value, _ = self.explain("deployment.targets")
        return [str(t) for t in value] if isinstance(value, list) else [str(value)]

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

    def set_default_platform(self, platform_id: str) -> None:
        """Set ``deployment.default_platform`` and union it into ``targets``.

        Never removes other enabled targets (multi-platform declarations
        survive a platform switch). Pops the legacy ``runtime.platform``
        key in the same write. No-op — no file touch — when both the
        default and the target membership already match.
        """
        with self._config_lock():
            raw = self.load_raw()
            deployment_raw = raw.get("deployment")
            deployment = dict(deployment_raw) if isinstance(deployment_raw, dict) else {}
            targets = [str(t) for t in deployment.get("targets") or []]
            legacy = (raw.get("runtime") or {}).get("platform")
            if (
                deployment.get("default_platform") == platform_id
                and platform_id in targets
                and legacy is None
            ):
                return
            deployment["default_platform"] = platform_id
            if platform_id not in targets:
                targets.append(platform_id)
            deployment["targets"] = targets
            raw["deployment"] = deployment
            runtime = raw.get("runtime")
            if isinstance(runtime, dict):
                runtime = dict(runtime)
                runtime.pop("platform", None)
                if runtime:
                    raw["runtime"] = runtime
                else:
                    raw.pop("runtime", None)
            self._write_raw(raw)
            self._cache = None

    def set_languages(self, languages: list[str]) -> None:
        """Write ``project.languages``, preserving every other field.

        Same verbatim-read / single-key-patch / atomic-write discipline as
        :meth:`set_default_platform`, so unrelated keys keep their order.
        """
        with self._config_lock():
            raw = self.load_raw()
            raw.setdefault("project", {})["languages"] = list(languages)
            self._write_raw(raw)
            self._cache = None

    def set_design_tool(self, design_tool: str) -> None:
        """Write ``project.design_tool``, preserving every other field.

        Same verbatim-read / single-key-patch / atomic-write discipline as
        :meth:`set_default_platform`, so unrelated keys keep their order.
        """
        with self._config_lock():
            raw = self.load_raw()
            raw.setdefault("project", {})["design_tool"] = design_tool
            self._write_raw(raw)
            self._cache = None

    def set_context_mode(self, mode: str) -> None:
        """Write ``context.mode``, preserving every other field.

        Same verbatim-read / single-key-patch / atomic-write discipline as
        :meth:`set_default_platform`, so unrelated keys keep their order.
        """
        with self._config_lock():
            raw = self.load_raw()
            raw.setdefault("context", {})["mode"] = mode
            self._write_raw(raw)
            self._cache = None

    def describe_platform_change(self, platform_id: str) -> dict[str, Any] | None:
        """Return a description of what ``set_default_platform`` would change.

        Returns ``None`` when the file would remain unchanged. Otherwise
        returns ``{"field": "deployment.default_platform", "before": <old>,
        "after": <new>}`` — suitable for ``--dry-run`` / ``--show-diff``.
        """
        from cataforge.core.platform_id import default_platform_from_config_data

        raw = self.load_raw()
        current = default_platform_from_config_data(raw)
        targets = (raw.get("deployment") or {}).get("targets") or []
        legacy = (raw.get("runtime") or {}).get("platform")
        if current == platform_id and platform_id in targets and legacy is None:
            return None
        return {
            "field": "deployment.default_platform",
            "before": current,
            "after": platform_id,
        }

    def _config_lock(self) -> AbstractContextManager[None]:
        from cataforge.utils.locks import file_lock

        return file_lock(
            self._paths.config_lock,
            timeout=10.0,
            ttl_seconds=60.0,
            owner="config-write",
        )

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
