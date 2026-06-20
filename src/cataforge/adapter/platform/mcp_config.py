"""MCP server configuration and TOML serialization for platform adapters."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cataforge.core.errors import CataforgeError, ConfigError
from cataforge.core.io import read_json
from cataforge.utils.atomic_write import atomic_write_text


def neutral_remote_payload(payload: dict[str, Any], *, type_key: bool) -> dict[str, Any]:
    """Render a neutral ``{transport, url}`` MCP payload into a JSON-native remote
    entry; pass stdio payloads through unchanged.

    ``type_key=True`` emits a ``type`` field (Claude Code's ``.mcp.json``);
    ``type_key=False`` omits it (Cursor infers transport from ``url``).
    """
    if not payload.get("url") or payload.get("command"):
        return payload
    transport = str(payload.get("transport") or "http").lower()
    if transport == "streamable_http":
        transport = "http"
    out: dict[str, Any] = {}
    if type_key:
        out["type"] = transport
    out["url"] = str(payload["url"])
    headers = payload.get("headers")
    if isinstance(headers, dict) and headers:
        out["headers"] = headers
    return out


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
            raw = read_json(path)
            if isinstance(raw, dict):
                data = raw
        except ConfigError as exc:
            raise CataforgeError(
                f"existing config corrupted (cannot merge): {path} ({exc}). "
                f"Fix or remove the file and retry."
            ) from exc
        except OSError as exc:
            raise CataforgeError(f"cannot read existing config: {path} ({exc}).") from exc

    mcp = data.setdefault("mcp", {})
    mcp[server_id] = mcp_entry
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
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
        existing = path.read_text() if path.is_file() else ""
    except OSError as exc:
        raise CataforgeError(f"cannot read existing config: {path} ({exc}).") from exc
    section = _render_codex_mcp_section(server_id, server_config)
    merged = _replace_toml_mcp_section(existing, server_id, section)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, merged)
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
            lines.append(f"{_toml_key(str(k))} = {_toml_value(v)}")

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
