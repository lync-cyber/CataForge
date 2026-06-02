"""Tests for merge helpers raising on corrupt JSON instead of silently clearing."""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.adapter.platform.helpers import (
    merge_codex_mcp_server,
    merge_json_key,
    merge_opencode_project_mcp,
)
from cataforge.core.errors import CataforgeError

_BROKEN_JSON = '{ "broken": '
_VALID_JSON = '{"mcpServers": {"existing": {"command": "keep-me"}}}\n'
_VALID_OPENCODE = '{"mcp": {"existing": {"type": "local", "enabled": true}}}\n'


class TestMergeJsonKey:
    def test_corrupt_json_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".mcp.json"
        cfg.write_text(_BROKEN_JSON, encoding="utf-8")

        with pytest.raises(CataforgeError, match="corrupted"):
            merge_json_key(cfg, "mcpServers.new", {"command": "x"})

    def test_file_unchanged_after_corrupt_raise(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".mcp.json"
        cfg.write_text(_BROKEN_JSON, encoding="utf-8")

        with pytest.raises(CataforgeError):
            merge_json_key(cfg, "mcpServers.new", {"command": "x"})

        assert cfg.read_text(encoding="utf-8") == _BROKEN_JSON

    def test_valid_json_merges(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".mcp.json"
        cfg.write_text(_VALID_JSON, encoding="utf-8")

        merge_json_key(cfg, "mcpServers.added", {"command": "new-tool"})

        import json

        result = json.loads(cfg.read_text(encoding="utf-8"))
        assert "existing" in result["mcpServers"]
        assert "added" in result["mcpServers"]

    def test_new_file_creates(self, tmp_path: Path) -> None:
        cfg = tmp_path / "new.json"
        assert not cfg.exists()

        merge_json_key(cfg, "mcpServers.added", {"command": "x"})

        import json

        result = json.loads(cfg.read_text(encoding="utf-8"))
        assert "added" in result["mcpServers"]


class TestMergeOpencodeProjectMcp:
    def test_corrupt_json_raises(self, tmp_path: Path) -> None:
        cfg = tmp_path / "opencode.json"
        cfg.write_text(_BROKEN_JSON, encoding="utf-8")

        with pytest.raises(CataforgeError, match="corrupted"):
            merge_opencode_project_mcp(tmp_path, "my-server", {"command": "x", "args": []})

    def test_file_unchanged_after_corrupt_raise(self, tmp_path: Path) -> None:
        cfg = tmp_path / "opencode.json"
        cfg.write_text(_BROKEN_JSON, encoding="utf-8")

        with pytest.raises(CataforgeError):
            merge_opencode_project_mcp(tmp_path, "my-server", {"command": "x", "args": []})

        assert cfg.read_text(encoding="utf-8") == _BROKEN_JSON

    def test_valid_json_merges(self, tmp_path: Path) -> None:
        cfg = tmp_path / "opencode.json"
        cfg.write_text(_VALID_OPENCODE, encoding="utf-8")

        merge_opencode_project_mcp(tmp_path, "added-server", {"command": "y", "args": []})

        import json

        result = json.loads(cfg.read_text(encoding="utf-8"))
        assert "existing" in result["mcp"]
        assert "added-server" in result["mcp"]


class TestMergeCodexMcpServer:
    def test_valid_toml_merges(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[mcp_servers.existing]\ncommand = ["keep"]\nenabled = true\n',
            encoding="utf-8",
        )

        merge_codex_mcp_server(cfg, "added", {"command": "z", "args": []})

        content = cfg.read_text(encoding="utf-8")
        assert "mcp_servers.existing" in content
        assert "mcp_servers.added" in content

    def test_new_file_creates(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        assert not cfg.exists()

        merge_codex_mcp_server(cfg, "new-server", {"command": "z", "args": []})

        assert cfg.is_file()
        assert "mcp_servers.new-server" in cfg.read_text(encoding="utf-8")
