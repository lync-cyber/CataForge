"""Tests for penpot_cmd using the public get_config interface."""

from __future__ import annotations

import inspect

from cataforge.integrations import penpot


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
    from cataforge.cli import penpot_cmd

    source = inspect.getsource(penpot_cmd)
    assert "penpot._get_config" not in source
    assert "penpot.get_config" in source
