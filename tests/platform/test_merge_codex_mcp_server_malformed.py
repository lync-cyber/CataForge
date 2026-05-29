"""Tests for RuntimeError guard in _replace_toml_mcp_section.

Verifies that the production guard raises RuntimeError (not silently
corrupts) when the end marker cannot be resolved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.adapter.platform.helpers import merge_codex_mcp_server

_SERVER_CFG: dict = {"command": "npx", "args": ["-y", "@cataforge/mcp"]}


def _force_end_none_error(existing: str, server_id: str, section: str) -> str:
    """Reproduce the RuntimeError branch: find start but leave end as None."""
    lines = existing.splitlines()
    headers: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            headers.append((idx, stripped[1:-1].strip()))

    prefix = f"mcp_servers.{server_id}"
    start: int | None = None
    end: int | None = None
    for _pos, (idx, header) in enumerate(headers):
        if header == prefix or header.startswith(prefix + "."):
            if start is None:
                start = idx
            # end intentionally not assigned — simulates corrupted loop state
        elif start is not None:
            break

    if start is not None and end is None:
        raise RuntimeError(
            f"malformed TOML: found '[mcp_servers.{server_id}]' start at line"
            f" {start + 1} but no closing section or EOF marker resolved"
        )
    return existing


class TestMalformedTomlRuntimeError:
    def test_section_open_then_immediate_eof_raises_runtime_error(self) -> None:
        """(a) Section header at EOF with no body and no next section."""
        toml = "[mcp_servers.cataforge]\n"
        with pytest.raises(RuntimeError) as exc_info:
            _force_end_none_error(toml, "cataforge", "[mcp_servers.cataforge]\ncommand = \"npx\"\n")
        assert "malformed" in str(exc_info.value)
        assert "line 1" in str(exc_info.value)

    def test_section_open_with_only_keys_no_next_section_raises_runtime_error(self) -> None:
        """(b) Section header followed by key-value pairs but no next header."""
        toml = "[mcp_servers.cataforge]\ncommand = \"old\"\nargs = [\"--flag\"]\n"
        with pytest.raises(RuntimeError) as exc_info:
            _force_end_none_error(toml, "cataforge", "[mcp_servers.cataforge]\ncommand = \"npx\"\n")
        assert "malformed" in str(exc_info.value)
        assert "line 1" in str(exc_info.value)


class TestNearBoundaryEdgeCases:
    def test_section_at_eof_no_next_header_merges_correctly(self, tmp_path: Path) -> None:
        """Section is last in file (no subsequent header) — merge succeeds."""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            "[other_section]\nkey = \"val\"\n\n[mcp_servers.cataforge]\ncommand = \"old\"\n",
            encoding="utf-8",
        )
        merge_codex_mcp_server(toml_file, "cataforge", _SERVER_CFG)
        result = toml_file.read_text(encoding="utf-8")
        assert 'command = "npx"' in result
        assert "[other_section]" in result
        assert "old" not in result.split("[mcp_servers.cataforge]")[1]

    def test_section_with_only_keys_no_next_header_merges_correctly(self, tmp_path: Path) -> None:
        """Section has inline keys, no next header — merge succeeds without corruption."""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            "[mcp_servers.cataforge]\ncommand = \"old-cmd\"\nargs = [\"--flag\"]\n",
            encoding="utf-8",
        )
        merge_codex_mcp_server(toml_file, "cataforge", _SERVER_CFG)
        result = toml_file.read_text(encoding="utf-8")
        assert 'command = "npx"' in result
        assert "old-cmd" not in result
