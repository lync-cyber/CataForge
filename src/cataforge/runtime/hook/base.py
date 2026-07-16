"""Hook infrastructure — cross-platform shared utilities for hook scripts.

Provides:
- read_hook_input(): unified stdin JSON reading
- hook_main(): hook entry decorator (logs failures to .hook-errors.jsonl)
- get_platform(): current runtime platform ID
- matches_capability(): cross-platform tool name matching
- extract_edited_paths(): file paths from edit-tool payloads (incl. apply_patch)
- matches_script_filters(): v2 schema filter evaluation
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import functools
import json
import logging
import os
import re
import sys
import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.platform_env import platform_from_env

logger = logging.getLogger("cataforge.runtime.hook")

HOOK_ERROR_LOG_MAX_BYTES = 256 * 1024


def read_hook_input() -> dict[str, Any]:
    """Read and parse stdin JSON with robust encoding handling."""
    from cataforge.core.io import read_stdin_utf8

    try:
        return dict(json.loads(read_stdin_utf8(errors="replace")))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, AttributeError) as e:
        logger.debug("Failed to parse hook stdin: %s", e)
        return {}


def get_platform() -> str:
    """Get the current runtime platform ID.

    Priority:
    1. CATAFORGE_PLATFORM env var (explicit user override)
    2. ``--cataforge-platform <id>`` argv stamped by the deploy-generated
       hook wrapper
    3. IDE-specific env var detection
    4. framework.json fallback — FAILS on a multi-platform project, where
       the shared default would silently mis-identify the session
    """
    explicit = os.environ.get("CATAFORGE_PLATFORM")
    if explicit:
        return explicit
    from_argv = _platform_from_argv()
    if from_argv is not None:
        return from_argv
    from_env = platform_from_env()
    if from_env is not None:
        return from_env
    return _detect_from_framework_json()


def _platform_from_argv() -> str | None:
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--cataforge-platform" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--cataforge-platform="):
            return arg.split("=", 1)[1]
    return None


def _detect_from_framework_json() -> str:
    from cataforge.core.paths import ProjectPaths, find_project_root_or_none

    root = find_project_root_or_none()
    if root is None:
        return "claude-code"
    try:
        from cataforge.core.platform_id import (
            default_platform_from_config_data,
            deployment_targets_from_config_data,
        )

        config = read_json(ProjectPaths(root).framework_json)
        targets = deployment_targets_from_config_data(config)
        if len(targets) > 1:
            raise RuntimeError(
                "ambiguous hook platform: project declares multiple deployment "
                f"targets {targets} and no explicit identity signal is present. "
                "Set CATAFORGE_PLATFORM or redeploy so the generated hook "
                "wrapper carries --cataforge-platform."
            )
        return default_platform_from_config_data(config) or "claude-code"
    except ConfigError:
        return "claude-code"


_hook_naming_cache: tuple[dict[str, str | None], dict[str, str]] | None = None
_tool_map_lock = threading.Lock()


def _load_hook_naming() -> tuple[dict[str, str | None], dict[str, str]]:
    """``(tool_map, hooks.tool_overrides)`` for the current platform.

    Hook payloads identify tools by hook-facing names, which may differ from
    the model-facing ``tool_map`` names (e.g. Codex ships tool ``shell`` but
    serializes hook ``tool_name: "Bash"``). ``hooks.tool_overrides`` carries
    those divergences — the same precedence the deploy-side matcher uses.
    """
    global _hook_naming_cache
    with _tool_map_lock:
        if _hook_naming_cache is not None:
            return _hook_naming_cache

        platform_id = get_platform()
        try:
            from cataforge.adapter.platform.registry import get_adapter

            adapter = get_adapter(platform_id)
            _hook_naming_cache = (adapter.get_tool_map(), dict(adapter.hook_tool_overrides))
        except Exception as e:
            logger.debug("Failed to load tool_map from adapter, using profile fallback: %s", e)
            _hook_naming_cache = _load_hook_naming_from_profile(platform_id)
        return _hook_naming_cache


def clear_tool_map_cache() -> None:
    global _hook_naming_cache
    with _tool_map_lock:
        _hook_naming_cache = None


def clear_spec_entry_cache() -> None:
    _spec_entry_for_script.cache_clear()


def _hook_naming_from_raw(raw: Any) -> tuple[dict[str, str | None], dict[str, str]] | None:
    if not (isinstance(raw, dict) and "tool_map" in raw):
        return None
    hooks = raw.get("hooks")
    overrides = hooks.get("tool_overrides") if isinstance(hooks, dict) else None
    return dict(raw["tool_map"]), dict(overrides) if isinstance(overrides, dict) else {}


def _load_hook_naming_from_profile(
    platform_id: str,
) -> tuple[dict[str, str | None], dict[str, str]]:
    """Load tool_map + hook tool_overrides from profile.yaml without the full
    adapter import chain.

    Falls back to Claude Code defaults only when no profile can be found.
    """

    from cataforge.core.paths import ProjectPaths, find_project_root_or_none

    # Try to find .cataforge/platforms/<id>/profile.yaml near the project root
    root = find_project_root_or_none()
    if root is not None:
        profile_yaml = ProjectPaths(root).platform_profile(platform_id)
        try:
            import yaml

            with open(profile_yaml) as f:
                parsed = _hook_naming_from_raw(yaml.safe_load(f))
            if parsed is not None:
                return parsed
        except (OSError, ValueError, ImportError) as exc:
            logger.debug("Failed to load profile.yaml for platform %r: %s", platform_id, exc)
        except Exception as exc:
            logger.debug(
                "Unexpected error loading profile.yaml for platform %r: %s", platform_id, exc
            )

        profile_json = profile_yaml.with_suffix(".json")
        if profile_json.is_file():
            try:
                parsed = _hook_naming_from_raw(read_json(profile_json))
                if parsed is not None:
                    return parsed
            except (OSError, ValueError) as exc:
                logger.debug("Failed to load profile.json for platform %r: %s", platform_id, exc)
            except Exception as exc:
                logger.debug(
                    "Unexpected error loading profile.json for platform %r: %s", platform_id, exc
                )

    # Last-resort fallback: hardcoded Claude Code defaults
    logger.debug("Using hardcoded Claude Code tool_map defaults")
    return {
        "file_read": "Read",
        "file_write": "Write",
        "file_edit": "Edit",
        "file_glob": "Glob",
        "file_grep": "Grep",
        "shell_exec": "Bash",
        "web_search": "WebSearch",
        "web_fetch": "WebFetch",
        "user_question": "AskUserQuestion",
        "agent_dispatch": "Agent",
    }, {}


def get_platform_tool_name(capability: str) -> str | None:
    return _load_hook_naming()[0].get(capability)


def _capability_names(capability: str) -> set[str]:
    """All hook-facing spellings for *capability* (tool_map ∪ tool_overrides).

    Override values may be matcher alternations ("Edit|Write") — split so
    membership tests compare single tool names.
    """
    tool_map, overrides = _load_hook_naming()
    names: set[str] = set()
    for value in (tool_map.get(capability), overrides.get(capability)):
        if value:
            names.update(part for part in value.split("|") if part)
    return names


def matches_capability(data: dict[str, Any], capability: str) -> bool:
    """Check if the hook's stdin tool_name matches a capability."""
    tool_name = data.get("tool_name", "")
    expected = _capability_names(capability)
    if capability == "file_edit":
        expected |= _capability_names("file_write")
    if not expected:
        return False
    return tool_name in expected


# apply_patch envelopes name each touched file on a "*** <verb> File:" line;
# "Move to" carries the rename target, which counts as a touched path too.
_APPLY_PATCH_PATH_RE = re.compile(
    r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.MULTILINE
)


def extract_edited_paths(data: dict[str, Any]) -> list[str]:
    """File paths touched by an edit-tool hook payload.

    ``tool_input.file_path`` / ``tool_input.path`` payloads carry one explicit
    path; Codex ``apply_patch`` payloads carry the whole patch in
    ``tool_input.command``, where each hunk names its file.
    """
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path")
    if path:
        return [str(path)]
    if data.get("tool_name") == "apply_patch":
        command = tool_input.get("command")
        if isinstance(command, str):
            return [m.strip() for m in _APPLY_PATCH_PATH_RE.findall(command)]
    return []


_DISPLAY_NAMES = {
    "claude-code": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex CLI",
    "opencode": "OpenCode",
}


def get_platform_display_name() -> str:
    return _DISPLAY_NAMES.get(get_platform(), "CataForge")


def hook_main(func: Callable[[], Any]) -> Callable[[], None]:
    """Hook entry decorator for ``observe`` scripts.

    Any uncaught exception is (a) written to ``.cataforge/.hook-errors.jsonl``
    with a timestamp + traceback so ``doctor`` can surface silent failures,
    (b) echoed to stderr when ``CATAFORGE_HOOK_DEBUG`` is set, and (c)
    converted to ``exit 0`` — an ``observe`` hook must never block the
    user's workflow by crashing.

    ``block`` hooks (e.g. ``guard_dangerous``) deliberately do *not* use
    this decorator: their ``sys.exit(2)`` must propagate to signal a block,
    which ``except SystemExit: raise`` would still respect, but swallowing
    other exceptions would mask broken blockers.  See
    ``tests/hook/test_script_contract.py`` for the static guard.
    """

    def wrapper() -> None:
        try:
            func()
        except SystemExit:
            raise
        except KeyboardInterrupt:
            # Ctrl+C is an explicit user signal to abort, not a hook
            # failure. Swallowing it into ``exit 0`` would let the
            # surrounding deploy / dispatch continue against the user's
            # stated wish (and hide the interrupt from any wrapping
            # CLI command that wants to print a "cancelled" message).
            raise
        except Exception as exc:
            _record_hook_error(func.__module__, func.__name__, exc)
            if os.environ.get("CATAFORGE_HOOK_DEBUG"):
                traceback.print_exc(file=sys.stderr)
            else:
                print(
                    f"[HOOK-ERROR] {func.__module__}.{func.__name__}: {exc}",
                    file=sys.stderr,
                )
            sys.exit(0)

    return wrapper


def _record_hook_error(module: str, func_name: str, exc: BaseException) -> None:
    """Append a structured failure record to ``.cataforge/.hook-errors.jsonl``.

    Best-effort: any failure to write the log is itself swallowed — the hook
    must never block because its diagnostics plumbing is broken.
    """
    try:
        from cataforge.core.paths import ProjectPaths, find_project_root_or_none

        root = find_project_root_or_none()
        if root is None:
            return
        log_path = ProjectPaths(root).hook_error_log
        log_path.parent.mkdir(parents=True, exist_ok=True)

        _rotate_if_too_large(log_path)

        record = {
            "ts": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
            "module": module,
            "func": func_name,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Swallow — observability plumbing must never break the hook itself.
        pass


def _rotate_if_too_large(log_path: Path) -> None:
    """Truncate the log if it gets unwieldy (naïve rotation).

    The goal is to stop the file from growing without bound when a hook is
    crashing on every call.  Users can always inspect it before rotation.
    """
    try:
        if log_path.is_file() and log_path.stat().st_size > HOOK_ERROR_LOG_MAX_BYTES:
            bak = log_path.with_suffix(log_path.suffix + ".1")
            if bak.exists():
                bak.unlink()
            log_path.rename(bak)
    except OSError:
        pass


# ---- schema v2 filter evaluation ---------------------------------------


@functools.cache
def _spec_entry_for_script(script_name: str) -> dict[str, Any] | None:
    """Locate the hooks.yaml entry for ``script_name``.

    Scripts may declare v2 filters (``matcher_file_pattern`` / ``matcher_
    command_pattern`` / ``matcher_agent_id``) that must be enforced at
    runtime because no IDE hook config supports them natively.  This helper
    reads the canonical spec and returns the raw entry (or ``None`` when
    the script is not declared, in which case all filters are "off").

    Results are cached per-process so repeated filter evaluations within a
    single hook invocation do not re-read and re-parse hooks.yaml.
    """
    try:
        from cataforge.runtime.hook.bridge import load_hooks_spec

        spec = load_hooks_spec()
    except Exception as exc:
        logger.debug("Failed to load hooks spec for script %r: %s", script_name, exc)
        return None

    for event_hooks in (spec.get("hooks") or {}).values():
        for entry in event_hooks or []:
            declared = str(entry.get("script", "")).replace(".py", "")
            if declared == script_name:
                return dict(entry)
    return None


def matches_script_filters(data: dict[str, Any], script_name: str | None = None) -> bool:
    """Return True when *data* satisfies all v2 filters declared for
    *script_name* in ``hooks.yaml``.

    Filters are opt-in; a spec entry with no filter keys always matches.

    ``script_name`` defaults to the *__main__* caller's module stem, which
    is what hook scripts want 99% of the time.
    """
    if script_name is None:
        script_name = _calling_script_name()
    if not script_name:
        return True

    entry = _spec_entry_for_script(script_name)
    if entry is None:
        return True

    tool_input = data.get("tool_input") or {}

    # --- file_path glob list --------------------------------------------
    patterns = entry.get("matcher_file_pattern")
    if patterns:
        raw_paths = extract_edited_paths(data)
        if not raw_paths:
            return False

        def _path_matches(raw: str) -> bool:
            normalised = raw.replace("\\", "/")
            basename = normalised.rsplit("/", 1)[-1]
            return any(
                fnmatch.fnmatch(normalised, p) or fnmatch.fnmatch(basename, p) for p in patterns
            )

        if not any(_path_matches(raw) for raw in raw_paths):
            return False

    # --- command regex list ---------------------------------------------
    regexes = entry.get("matcher_command_pattern")
    if regexes:
        command = str(tool_input.get("command", ""))
        if not command or not any(re.search(rx, command) for rx in regexes):
            return False

    # --- agent id allowlist ---------------------------------------------
    agent_ids = entry.get("matcher_agent_id")
    if agent_ids:
        candidate = (
            tool_input.get("subagent_type")
            or tool_input.get("agent_type")
            or tool_input.get("agent")
            or data.get("agent")
            or ""
        )
        if not candidate or candidate not in agent_ids:
            return False

    return True


def _calling_script_name() -> str | None:
    """Best-effort: pick up the hook script name from ``sys.argv[0]`` or
    the ``__main__`` module.  Returns ``None`` when we cannot determine it,
    at which point filters default to "allow" (safe default)."""
    try:
        import __main__

        spec = getattr(__main__, "__spec__", None)
        if spec and spec.name:
            # e.g. "cataforge.runtime.hook.scripts.lint_format"
            return str(spec.name).rsplit(".", 1)[-1]
        path = getattr(__main__, "__file__", None)
        if path:
            return Path(path).stem
    except Exception as exc:
        logger.debug("Could not determine calling script name: %s", exc)
    return None
