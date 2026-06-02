"""Tests: entry_point specs with untrusted commands are warned and skipped."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cataforge.core.schema.mcp_spec import MCPServerSpec
from cataforge.runtime.mcp.registry import MCPRegistry

_EP_IMPORT_PATH = "importlib.metadata.entry_points"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    return tmp_path


def _make_ep(name: str, spec: MCPServerSpec) -> MagicMock:
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = lambda: spec
    return ep


class TestRegistryUntrustedSpec:
    def test_untrusted_absolute_command_skipped_with_warning(
        self, project: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """entry_point returning /bin/sh must be warned about and not registered."""
        bad_spec = MCPServerSpec(id="pwned", command="/bin/sh", args=["-c", "echo pwned"])

        with (
            caplog.at_level(logging.WARNING, logger="cataforge.runtime.mcp"),
            patch(_EP_IMPORT_PATH, return_value=[_make_ep("bad-ep", bad_spec)]),
        ):
            reg = MCPRegistry(project)

        assert reg.get_server("pwned") is None, "untrusted spec must not appear in registry"
        warning_text = " ".join(caplog.messages)
        assert "/bin/sh" in warning_text, "warning must include the offending command"
        assert "untrusted command" in warning_text.lower()

    def test_trusted_python_command_registered(
        self, project: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """entry_point returning command='python' must be registered normally."""
        good_spec = MCPServerSpec(id="my-mcp", command="python", args=["-m", "my_mcp"])

        with (
            caplog.at_level(logging.WARNING, logger="cataforge.runtime.mcp"),
            patch(_EP_IMPORT_PATH, return_value=[_make_ep("good-ep", good_spec)]),
        ):
            reg = MCPRegistry(project)

        assert reg.get_server("my-mcp") is not None, "trusted spec must be registered"
        assert all("untrusted" not in msg.lower() for msg in caplog.messages), (
            "no warning should be emitted for a trusted command"
        )

    def test_untrusted_shell_command_warning_includes_command(
        self, project: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warning for an untrusted spec must name the specific command."""
        bad_spec = MCPServerSpec(id="shell-inject", command="bash", args=["-c", "id"])

        with (
            caplog.at_level(logging.WARNING, logger="cataforge.runtime.mcp"),
            patch(_EP_IMPORT_PATH, return_value=[_make_ep("shell-ep", bad_spec)]),
        ):
            reg = MCPRegistry(project)

        assert reg.get_server("shell-inject") is None

        warning_text = " ".join(caplog.messages)
        assert "bash" in warning_text, "warning must include the command 'bash'"

    def test_multiple_eps_only_good_ones_registered(
        self, project: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A mix of trusted and untrusted entry_points: only trusted ones land."""
        good = MCPServerSpec(id="good", command="node", args=["server.js"])
        bad = MCPServerSpec(id="bad", command="/usr/bin/curl", args=["http://evil.com"])

        with (
            caplog.at_level(logging.WARNING, logger="cataforge.runtime.mcp"),
            patch(
                _EP_IMPORT_PATH,
                return_value=[_make_ep("good-ep", good), _make_ep("bad-ep", bad)],
            ),
        ):
            reg = MCPRegistry(project)

        assert reg.get_server("good") is not None
        assert reg.get_server("bad") is None
        assert "/usr/bin/curl" in " ".join(caplog.messages)

    def test_trusted_prefixes_all_accepted(self, project: Path) -> None:
        """All TRUSTED_COMMAND_PREFIXES values must be accepted without warning."""
        from cataforge.core.schema.mcp_spec import TRUSTED_COMMAND_PREFIXES

        for executable in TRUSTED_COMMAND_PREFIXES:
            spec = MCPServerSpec(id=f"ep-{executable}", command=executable, args=[])
            with patch(_EP_IMPORT_PATH, return_value=[_make_ep(f"ep-{executable}", spec)]):
                reg = MCPRegistry(project)
            assert reg.get_server(f"ep-{executable}") is not None, f"'{executable}' must be trusted"


class TestIsTrustedCommandPathTraversal:
    """A relative path that climbs out of the project tree must not be
    waved through as a project-local binary."""

    def test_parent_dir_escape_rejected_posix(self, project: Path) -> None:
        spec = MCPServerSpec(id="x", command="../../evil.sh", args=[])
        assert MCPRegistry._is_trusted_command(spec) is False

    def test_parent_dir_escape_rejected_windows_sep(self, project: Path) -> None:
        spec = MCPServerSpec(id="x", command="..\\..\\evil.exe", args=[])
        assert MCPRegistry._is_trusted_command(spec) is False

    def test_local_relative_path_still_trusted(self, project: Path) -> None:
        spec = MCPServerSpec(id="x", command="./bin/tool", args=[])
        assert MCPRegistry._is_trusted_command(spec) is True

    def test_bare_name_behaviour_unchanged(self, project: Path) -> None:
        # Bare untrusted name stays untrusted; trusted prefix stays trusted.
        assert (
            MCPRegistry._is_trusted_command(MCPServerSpec(id="x", command="evil", args=[])) is False
        )
        assert (
            MCPRegistry._is_trusted_command(MCPServerSpec(id="x", command="python", args=[]))
            is True
        )
