"""Tests for penpot_cmd using the public get_config interface."""

from __future__ import annotations

import inspect

from cataforge.adapter.integrations import penpot


def test_penpot_uses_public_get_config() -> None:
    assert hasattr(penpot, "get_config")
    assert callable(penpot.get_config)
    assert not hasattr(penpot, "_get_config")


def test_get_config_returns_expected_keys() -> None:
    config = penpot.get_config()
    assert "penpot_dir" in config
    assert "penpot_port" in config
    assert "mcp_port" in config


def test_penpot_cmd_uses_public_get_config() -> None:
    from cataforge.interface.cli import penpot_cmd

    source = inspect.getsource(penpot_cmd)
    assert "penpot._get_config" not in source
    assert "penpot.get_config" in source


def test_penpot_remote_subcommand_registered() -> None:
    """`cataforge penpot remote` must be a registered click subcommand."""
    from cataforge.interface.cli import penpot_cmd

    cmd = penpot_cmd.penpot_group.get_command(None, "remote")
    assert cmd is not None, "`cataforge penpot remote` is not registered"
    assert cmd.help and "PENPOT_MCP_URL" in cmd.help


def test_penpot_init_and_doctor_registered() -> None:
    """Wave 3: init wizard and doctor must be click subcommands."""
    from cataforge.interface.cli import penpot_cmd

    init_cmd = penpot_cmd.penpot_group.get_command(None, "init")
    doctor_cmd = penpot_cmd.penpot_group.get_command(None, "doctor")
    assert init_cmd is not None, "`cataforge penpot init` is not registered"
    assert doctor_cmd is not None, "`cataforge penpot doctor` is not registered"


def test_penpot_group_help_lists_new_subcommands() -> None:
    """Group help should advertise the primary entry points."""
    from cataforge.interface.cli import penpot_cmd

    help_text = penpot_cmd.penpot_group.help or ""
    for needle in ("init", "remote", "doctor", "PENPOT_MCP_URL"):
        assert needle in help_text, f"group help missing {needle!r}"
