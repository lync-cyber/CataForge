"""Hook infrastructure — cross-platform shared utilities for hook scripts.

Provides:
- read_hook_input(): unified stdin JSON reading
- hook_main(): hook entry decorator (logs failures to .hook-errors.jsonl)
- get_platform(): current runtime platform ID
- matches_capability(): cross-platform tool name matching
- matches_script_filters(): v2 schema filter evaluation
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import logging
import os
import re
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger("cataforge.hook")

# Relative to the project root.  One JSONL per failure so ``doctor`` can
# cheaply tail-scan without parsing a whole stateful file.
HOOK_ERROR_LOG_REL = Path(".cataforge") / ".hook-errors.jsonl"
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
    1. CATAFORGE_PLATFORM env var
    2. IDE-specific env var detection
    3. framework.json fallback
    """
    explicit = os.environ.get("CATAFORGE_PLATFORM")
    if explicit:
        return explicit

    if os.environ.get("CURSOR_PROJECT_DIR"):
        return "cursor"
    if os.environ.get("CODEX_HOME"):
        return "codex"
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return "claude-code"

    return _detect_from_framework_json()


def _detect_from_framework_json() -> str:
    fj_path = Path(__file__).resolve().parent.parent.parent.parent / ".cataforge" / "framework.json"
    if not fj_path.is_file():
        fj_path2 = _find_framework_json()
        if fj_path2:
            fj_path = fj_path2

    try:
        with open(fj_path, encoding="utf-8") as f:
            config = json.load(f)
        return str(config.get("runtime", {}).get("platform", "claude-code"))
    except (OSError, json.JSONDecodeError):
        return "claude-code"


def _find_framework_json() -> Path | None:
    """Walk up from CWD looking for .cataforge/framework.json."""
    d = Path.cwd()
    while True:
        candidate = d / ".cataforge" / "framework.json"
        if candidate.is_file():
            return candidate
        parent = d.parent
        if parent == d:
            return None
        d = parent


_tool_map_cache: dict[str, str | None] | None = None


def _load_tool_map() -> dict[str, str | None]:
    global _tool_map_cache
    if _tool_map_cache is not None:
        return _tool_map_cache

    platform_id = get_platform()
    try:
        from cataforge.platform.registry import get_adapter

        adapter = get_adapter(platform_id)
        _tool_map_cache = adapter.get_tool_map()
    except Exception as e:
        logger.debug("Failed to load tool_map from adapter, using profile fallback: %s", e)
        _tool_map_cache = _load_tool_map_from_profile(platform_id)
    return _tool_map_cache


def _load_tool_map_from_profile(platform_id: str) -> dict[str, str | None]:
    """Load tool_map directly from profile.yaml without full adapter import chain.

    Falls back to Claude Code defaults only when no profile can be found.
    """
    import json as _json

    # Try to find .cataforge/platforms/<id>/profile.yaml near the project root
    fj_path = _find_framework_json()
    if fj_path:
        profile_yaml = fj_path.parent / "platforms" / platform_id / "profile.yaml"
        try:
            import yaml

            with open(profile_yaml, encoding="utf-8") as f:
                profile = yaml.safe_load(f)
            if isinstance(profile, dict) and "tool_map" in profile:
                return dict(profile["tool_map"])
        except Exception:
            pass

        profile_json = profile_yaml.with_suffix(".json")
        if profile_json.is_file():
            try:
                raw = _json.loads(profile_json.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "tool_map" in raw:
                    return dict(raw["tool_map"])
            except Exception:
                pass

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
    }


def get_platform_tool_name(capability: str) -> str | None:
    return _load_tool_map().get(capability)


def matches_capability(data: dict[str, Any], capability: str) -> bool:
    """Check if the hook's stdin tool_name matches a capability."""
    tool_name = data.get("tool_name", "")
    expected = get_platform_tool_name(capability)

    if expected is None:
        return False

    if capability == "file_edit":
        edit_tools = {expected}
        write_name = get_platform_tool_name("file_write")
        if write_name:
            edit_tools.add(write_name)
        return tool_name in edit_tools

    return tool_name == expected


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
        fj = _find_framework_json()
        if fj is None:
            return
        # fj = <root>/.cataforge/framework.json — the log lives next to it.
        project_root = fj.parent.parent
        log_path = project_root / HOOK_ERROR_LOG_REL
        log_path.parent.mkdir(parents=True, exist_ok=True)

        _rotate_if_too_large(log_path)

        record = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "module": module,
            "func": func_name,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        }
        with open(log_path, "a", encoding="utf-8") as f:
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


def _spec_entry_for_script(script_name: str) -> dict[str, Any] | None:
    """Locate the hooks.yaml entry for ``script_name``.

    Scripts may declare v2 filters (``matcher_file_pattern`` / ``matcher_
    command_pattern`` / ``matcher_agent_id``) that must be enforced at
    runtime because no IDE hook config supports them natively.  This helper
    reads the canonical spec and returns the raw entry (or ``None`` when
    the script is not declared, in which case all filters are "off").
    """
    try:
        from cataforge.hook.bridge import load_hooks_spec

        spec = load_hooks_spec()
    except Exception:
        return None

    for event_hooks in (spec.get("hooks") or {}).values():
        for entry in event_hooks or []:
            declared = str(entry.get("script", "")).replace(".py", "")
            if declared == script_name:
                return dict(entry)
    return None


def matches_script_filters(
    data: dict[str, Any], script_name: str | None = None
) -> bool:
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
        raw_path = tool_input.get("file_path") or tool_input.get("path") or ""
        if not raw_path:
            return False
        normalised = str(raw_path).replace("\\", "/")
        basename = normalised.rsplit("/", 1)[-1]
        if not any(
            fnmatch.fnmatch(normalised, p) or fnmatch.fnmatch(basename, p)
            for p in patterns
        ):
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
        import __main__  # type: ignore[import]

        spec = getattr(__main__, "__spec__", None)
        if spec and spec.name:
            # e.g. "cataforge.hook.scripts.lint_format"
            return spec.name.rsplit(".", 1)[-1]
        path = getattr(__main__, "__file__", None)
        if path:
            return Path(path).stem
    except Exception:
        pass
    return None
