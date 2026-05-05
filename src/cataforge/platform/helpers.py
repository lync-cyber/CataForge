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


def symlink_or_copy(source: Path, target: Path, *, dry_run: bool = False) -> list[str]:
    """Create symlink (Unix), junction (Windows), or copy as fallback.

    The dry-run message is deliberately label-free ("would link"): this
    helper is used for rules, skills, and generic cross-directory mirrors.
    Callers that want a more specific label should emit their own action
    line instead of / in addition to calling this helper.
    """
    import platform as platform_mod

    if dry_run:
        return [f"would link {target} ← {source} (symlink|junction|copy)"]

    _remove_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    if platform_mod.system() != "Windows":
        rel = os.path.relpath(source, target.parent)
        target.symlink_to(rel)
        return [f"{target} → {source} (symlink)"]

    try:
        import subprocess

        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            check=True,
            capture_output=True,
        )
        return [f"{target} → {source} (junction)"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        if os.path.lexists(str(target)):
            _remove_target(target)
        shutil.copytree(source, target)
        return [f"{target} ← {source} (copy)"]


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
        except (json.JSONDecodeError, OSError):
            data = {}
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
        except (json.JSONDecodeError, OSError):
            data = {}

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

    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
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
        assert end is not None
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
