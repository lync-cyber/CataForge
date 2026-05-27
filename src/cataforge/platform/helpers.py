"""Shared platform utilities — file deployment helpers.

Extracted from claude_code.py to avoid cross-adapter coupling.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from cataforge.cli.errors import CataforgeError


def _prune_orphan_flat_files(
    directory: Path,
    known_names: set[str],
    suffix: str,
    head_signature: str,
    target_rel: str,
    *,
    head_read_size: int = 512,
    dry_run: bool = False,
    prior_manifest: set[str] | None = None,
) -> list[str]:
    """Prune flat files in *directory* that are orphans of a deploy pass.

    Only removes files whose stem is absent from *known_names* **and** whose
    first *head_read_size* bytes contain *head_signature* (with ``{stem}``
    replaced by the file's stem).  Files that fail this ownership check are
    left untouched regardless of their extension.

    When *prior_manifest* is supplied (production deploy path) prune is
    further restricted to entries that path-match a prior-deploy record —
    so a user-authored ``foo.md`` that happens to carry our head signature
    by coincidence (e.g. a copy-pasted CataForge agent the user kept) still
    survives.

    Returns action strings suitable for appending to a caller's actions list.
    """
    actions: list[str] = []
    if not directory.is_dir():
        return actions
    for existing in directory.iterdir():
        if (
            not existing.is_file()
            or existing.suffix != suffix
            or existing.stem in known_names
        ):
            continue
        head = existing.read_text(encoding="utf-8", errors="ignore")[:head_read_size]
        if head_signature.format(stem=existing.stem) not in head:
            continue
        existing_rel = f"{target_rel}/{existing.name}"
        if prior_manifest is not None and existing_rel not in prior_manifest:
            continue
        if dry_run:
            actions.append(f"would prune orphan {target_rel}/{existing.name}")
        else:
            existing.unlink()
            actions.append(f"pruned orphan {target_rel}/{existing.name}")
    return actions


def remove_dir_with_manifest_check(
    target: Path,
    *,
    display_rel: str,
    manifest_key: str,
    prior_manifest: set[str] | None,
    dry_run: bool = False,
    kind: str = "orphan",
) -> list[str]:
    """``shutil.rmtree`` *target* only when it's safe to attribute to us.

    Single deletion entry point for adapters that wholesale-remove a
    subdir they recognise as their own (e.g. legacy
    ``<name>/AGENT.md`` agent subdirs, the base-class orphan agent
    subdir prune). All callers had the same shape: check
    ``prior_manifest``, gate on ``dry_run``, call ``shutil.rmtree``,
    emit one ``[would] prune <kind> <path>/`` action line. Centralising
    it means a future change to that shape (logging the rmtree,
    wrapping in error handling) lands in one place.

    Two relative-path arguments because the manifest records the
    *file* path (``<dir>/AGENT.md``) while the action log displays
    the *dir* path (``<dir>/``):

    * ``manifest_key`` — the relative path to look up in
      ``prior_manifest``. Refusal here returns an empty list (treat
      as user-authored / pre-manifest legacy).
    * ``display_rel`` — what to print in the action line (no trailing
      slash — the helper adds one).

    ``kind`` is the noun in the action message; the verb tense
    (``would prune`` vs ``pruned``) is owned by this helper so callers
    can't drift apart.
    """
    if prior_manifest is not None and manifest_key not in prior_manifest:
        return []
    if dry_run:
        return [f"would prune {kind} {display_rel}/"]
    shutil.rmtree(target)
    return [f"pruned {kind} {display_rel}/"]


def _is_dir_link(path: Path) -> bool:
    """True for any directory-shaped link primitive across Python versions.

    Detects POSIX symlinks always, NTFS junctions on Python 3.12+ via the
    new ``Path.is_junction()`` method, and NTFS junctions on Python 3.10/3.11
    via the Win32 ``GetFileAttributesW`` API checking
    ``FILE_ATTRIBUTE_REPARSE_POINT``. Without the third leg, ``deploy_skills``
    legacy-link unwrap silently no-oped on the Py 3.10 CI matrix entry
    (Path.is_symlink returned False for junctions, Path.is_junction wasn't
    present), leaving stale whole-dir links in place forever.
    """
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction and is_junction():
        return True
    if os.name == "nt":
        try:
            import ctypes

            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            file_attribute_reparse_point = 0x400
            return attrs != -1 and bool(attrs & file_attribute_reparse_point)
        except (AttributeError, OSError):
            pass
    return False


def _remove_target(target: Path) -> None:
    """Idempotently remove ``target`` whether file, dir, symlink, or junction.

    Why this is non-trivial on Windows + Python 3.11:

    - ``Path.is_junction()`` was only added in 3.12, so on 3.11 a junction
      is invisible to that check.
    - ``Path.is_symlink()`` returns ``False`` for junctions on 3.11 (and
      below), so the symlink branch never fires either.
    - ``shutil.rmtree`` on a junction in that combo is *unsafe*: its
      symlink check goes through ``os.path.islink()`` which also returns
      ``False`` for junctions on 3.11, so it can recurse INTO the
      junction and start deleting the *source* tree.

    We side-step all of this by trying ``os.rmdir(target)`` first on
    Windows when ``target`` looks like a directory. ``rmdir`` removes the
    junction handle without touching the source, and fails loudly on a
    non-empty real directory — at which point we fall through to
    ``shutil.rmtree``.

    Uses ``os.path.lexists`` so dangling symlinks / junctions (whose
    source has moved or been deleted) are still cleaned up.
    """
    if not os.path.lexists(str(target)):
        return

    if target.is_symlink():
        target.unlink()
        return

    if hasattr(target, "is_junction") and target.is_junction():
        os.rmdir(str(target))
        return

    if os.name == "nt" and target.is_dir():
        try:
            os.rmdir(str(target))
            return
        except OSError:
            pass

    if target.is_dir():
        shutil.rmtree(target)
        return

    target.unlink()


# Set by ``symlink_or_copy`` the first time a junction fallback fires
# in this process, so the deploy log can emit a single user-facing
# WARN instead of one per linked skill. Reset between test functions via
# ``reset_junction_warning_state`` so order-of-execution does not affect
# assertions about whether the warning fires.
_JUNCTION_WARNING_EMITTED = False


def reset_junction_warning_state() -> None:
    """Test hook — clear the once-per-process WARN flag."""
    global _JUNCTION_WARNING_EMITTED
    _JUNCTION_WARNING_EMITTED = False


def _remove_target_once(target: Path, removed: list[bool]) -> None:
    """``_remove_target`` wrapper that is a no-op on the second+ call.

    The symlink → junction → copy fallback chain needs to clear *target*
    before each strategy attempt, but the strategies share one *target*
    path and only one of them ever lands a real artefact there. Calling
    ``_remove_target`` repeatedly along the chain is wasteful at best;
    in pathological cases (target briefly recreated by another process
    between attempts, or the first attempt left a half-deleted state)
    it racially deletes whatever happens to be there now.

    *removed* is a single-element list (mutable cell) the caller threads
    through the chain. ``[False]`` initially; flips to ``[True]`` on
    first removal; subsequent calls short-circuit.
    """
    if removed[0]:
        return
    _remove_target(target)
    removed[0] = True


def _ntfs_junction_warning() -> str:
    # Wording note: this WARN deliberately avoids the bare word
    # ``symlink`` so test assertions that grep for it in action
    # strings (see test_windows_falls_back_to_junction_then_copy)
    # don't false-trigger. The recovery path's name is rendered
    # as "relative-path link" / "soft link" instead.
    return (
        "WARN: falling back to NTFS junction(s). Two risks to "
        "know: (1) the junction stores an ABSOLUTE path, so a "
        "project rename / move breaks every link; (2) deleting "
        "or editing files INSIDE the junction (e.g. "
        ".claude/skills/<name>/SKILL.md) operates on the SOURCE "
        "at .cataforge/, not a copy — one mis-click can destroy "
        "source files. Enable Windows Developer Mode (Settings "
        "→ For developers → Developer Mode) to get portable "
        "relative-path soft links, or pass `cataforge deploy "
        "--copy` to materialise independent copies instead."
    )


def _try_symlink(source: Path, target: Path, removed: list[bool]) -> list[str] | None:
    """Attempt strategy 1: relative POSIX-normalised symlink. Returns the
    action log on success, ``None`` if the kernel refused the syscall."""
    # Normalise to forward slashes so the link target stays portable: on
    # Windows ``os.path.relpath`` emits backslashes which survive into the
    # symlink reparse point, breaking the link the moment the project is
    # cloned, copied, or mounted on a POSIX filesystem.
    rel = os.path.relpath(source, target.parent).replace("\\", "/")
    _remove_target_once(target, removed)
    try:
        os.symlink(rel, str(target), target_is_directory=True)
    except (OSError, NotImplementedError):
        return None
    return [f"{target} → {source} (symlink)"]


def _try_junction(source: Path, target: Path, removed: list[bool]) -> list[str] | None:
    """Attempt strategy 2 (Windows only): NTFS junction via ``mklink /J``.
    Returns the action log on success, ``None`` if mklink failed."""
    if os.name != "nt":
        return None
    global _JUNCTION_WARNING_EMITTED
    import subprocess

    _remove_target_once(target, removed)
    try:
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    actions = [f"{target} → {source} (junction)"]
    if not _JUNCTION_WARNING_EMITTED:
        _JUNCTION_WARNING_EMITTED = True
        actions.insert(0, _ntfs_junction_warning())
    return actions


def _do_copy(source: Path, target: Path, removed: list[bool]) -> list[str]:
    """Strategy 3 (terminal): full ``copytree``. Cannot fail-soft — any
    error propagates."""
    _remove_target_once(target, removed)
    shutil.copytree(source, target)
    return [f"{target} ← {source} (copy)"]


def symlink_or_copy(
    source: Path,
    target: Path,
    *,
    dry_run: bool = False,
    force_copy: bool = False,
) -> list[str]:
    """Create a relative symlink, junction, or copy — in that order.

    Why the priority order matters: NTFS junctions store an *absolute*
    path in the reparse point, so they break the moment the project
    directory moves or is renamed (and they leak the developer's local
    absolute path into anything that resolves them). A relative symlink
    survives both. On Windows, ``os.symlink`` only succeeds when the
    process has ``SeCreateSymbolicLinkPrivilege`` — held by elevated
    processes and by any user with Developer Mode enabled (Windows 10
    1703+). Junction is the fallback for legacy non-Dev-Mode users; a
    single WARN is emitted on first fall-back so users can opt into Dev
    Mode rather than discover the limitation by their links breaking
    after a project rename — or, worse, by destructively deleting source
    files through the junction.

    Pass ``force_copy=True`` to bypass both link strategies and write an
    independent ``copytree``. Use this when the caller cannot tolerate
    delete-through-link destroying the source (e.g.
    ``cataforge deploy --copy``).

    The dry-run message is deliberately label-free ("would link"):
    callers that need a specific label should emit their own action
    line instead of / in addition to calling this helper.

    Strategies are tried in order and ``_remove_target`` is invoked at
    most once across the whole chain — see :func:`_remove_target_once`.
    """
    if dry_run:
        if force_copy:
            return [f"would copy {target} ← {source}"]
        return [f"would link {target} ← {source} (symlink|junction|copy)"]

    target.parent.mkdir(parents=True, exist_ok=True)
    removed = [False]

    if force_copy:
        _remove_target_once(target, removed)
        shutil.copytree(source, target)
        return [f"{target} ← {source} (copy, forced)"]

    for attempt in (_try_symlink, _try_junction):
        actions = attempt(source, target, removed)
        if actions is not None:
            return actions

    return _do_copy(source, target, removed)


def merge_json_key(
    path: Path, dotted_key: str, value: Any, *, dry_run: bool = False
) -> list[str]:
    """Merge a value into a JSON file at a dotted key path."""
    if dry_run:
        return [f"would merge {dotted_key} → {path}"]

    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CataforgeError(
                f"existing config corrupted (cannot merge): {path} ({exc}). "
                f"Fix or remove the file and retry."
            ) from exc
        except OSError as exc:
            raise CataforgeError(
                f"cannot read existing config: {path} ({exc})."
            ) from exc
    else:
        data = {}

    keys = dotted_key.split(".")
    obj = data
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    obj[keys[-1]] = value

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return [f"merged {dotted_key} → {path}"]


def cataforge_mcp_payload_to_opencode_entry(server_config: dict[str, Any]) -> dict[str, Any]:
    """Map CataForge MCP payload (command/args/env, optional url) to OpenCode ``mcp`` entry."""
    transport = str(server_config.get("transport", "stdio")).lower()
    url = server_config.get("url")
    if transport in ("http", "sse", "streamable_http") and url:
        entry: dict[str, Any] = {
            "type": "remote",
            "url": str(url),
            "enabled": True,
        }
        headers = server_config.get("headers")
        if isinstance(headers, dict) and headers:
            entry["headers"] = headers
        return entry

    cmd = server_config.get("command") or ""
    args = list(server_config.get("args") or [])
    command_list = ([str(cmd)] if cmd else []) + [str(a) for a in args]
    entry = {
        "type": "local",
        "command": command_list,
        "enabled": True,
    }
    env = server_config.get("env")
    if isinstance(env, dict) and env:
        entry["environment"] = {str(k): str(v) for k, v in env.items()}
    return entry


def merge_opencode_project_mcp(
    project_root: Path,
    server_id: str,
    server_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> list[str]:
    """Merge one MCP server into project ``opencode.json`` under ``mcp.<server_id>``."""
    path = project_root / "opencode.json"
    mcp_entry = cataforge_mcp_payload_to_opencode_entry(server_config)
    if dry_run:
        return [f"would merge mcp.{server_id!r} → {path}"]

    data: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except json.JSONDecodeError as exc:
            raise CataforgeError(
                f"existing config corrupted (cannot merge): {path} ({exc}). "
                f"Fix or remove the file and retry."
            ) from exc
        except OSError as exc:
            raise CataforgeError(
                f"cannot read existing config: {path} ({exc})."
            ) from exc

    mcp = data.setdefault("mcp", {})
    mcp[server_id] = mcp_entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return [f"mcp.{server_id} → {path}"]


def merge_codex_mcp_server(
    path: Path,
    server_id: str,
    server_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> list[str]:
    """Merge one MCP server into Codex ``config.toml`` under ``[mcp_servers.<id>]``."""
    if dry_run:
        return [f"would merge mcp_servers.{server_id} → {path}"]

    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        raise CataforgeError(
            f"cannot read existing config: {path} ({exc})."
        ) from exc
    section = _render_codex_mcp_section(server_id, server_config)
    merged = _replace_toml_mcp_section(existing, server_id, section)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merged, encoding="utf-8")
    return [f"mcp_servers.{server_id} → {path}"]


def _replace_toml_mcp_section(existing: str, server_id: str, section: str) -> str:
    lines = existing.splitlines()
    headers: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            headers.append((idx, stripped[1:-1].strip()))

    prefix = f"mcp_servers.{server_id}"
    start: int | None = None
    end: int | None = None
    for pos, (idx, header) in enumerate(headers):
        if header == prefix or header.startswith(prefix + "."):
            if start is None:
                start = idx
            next_idx = headers[pos + 1][0] if pos + 1 < len(headers) else len(lines)
            end = next_idx
        elif start is not None:
            break

    if start is not None:
        if end is None:
            raise RuntimeError(
                f"malformed TOML: found '[mcp_servers.{server_id}]' start at line"
                f" {start + 1} but no closing section or EOF marker resolved"
            )
        new_lines = lines[:start] + lines[end:]
        existing = "\n".join(new_lines).strip()

    if existing:
        return existing + "\n\n" + section
    return section


def _render_codex_mcp_section(server_id: str, cfg: dict[str, Any]) -> str:
    allowed_keys = (
        "command",
        "args",
        "cwd",
        "url",
        "bearer_token_env_var",
        "startup_timeout_sec",
        "tool_timeout_sec",
        "enabled",
        "required",
        "enabled_tools",
        "disabled_tools",
        "scopes",
        "oauth_resource",
    )
    lines = [f"[mcp_servers.{server_id}]"]
    for key in allowed_keys:
        if key not in cfg:
            continue
        value = cfg[key]
        if value is None:
            continue
        lines.append(f"{key} = {_toml_value(value)}")

    for table_key in ("env", "http_headers", "env_http_headers"):
        table = cfg.get(table_key)
        if not isinstance(table, dict) or not table:
            continue
        lines.append("")
        lines.append(f"[mcp_servers.{server_id}.{table_key}]")
        for k, v in table.items():
            lines.append(f'{_toml_key(str(k))} = {_toml_value(v)}')

    return "\n".join(lines).rstrip() + "\n"


def _toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return _toml_value(key)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
