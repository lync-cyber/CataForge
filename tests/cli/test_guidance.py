"""Tests for cataforge.interface.cli.guidance — next-step registry."""

from __future__ import annotations

from cataforge.interface.cli.guidance import (
    NEXT_STEPS,
    has_next_steps,
    print_next_steps,
)


def test_known_keys_exist() -> None:
    """The keys subcommands cite must be registered."""
    required = {
        "setup-done",
        "setup-deployed",
        "deploy-done",
        "upgrade-applied",
        "upgrade-up-to-date",
        "doctor-pass",
        "bootstrap-done",
        "penpot-mcp-up",
    }
    assert required.issubset(NEXT_STEPS.keys()), (
        f"missing keys: {required - NEXT_STEPS.keys()}"
    )


def test_terminal_keys_are_empty_lists() -> None:
    """Keys that should not chain a follow-up must be explicitly empty."""
    assert NEXT_STEPS["bootstrap-done"] == []
    assert NEXT_STEPS["doctor-pass"] == []
    assert NEXT_STEPS["upgrade-up-to-date"] == []


def test_has_next_steps_reflects_registry() -> None:
    assert has_next_steps("deploy-done") is True
    assert has_next_steps("doctor-pass") is False
    assert has_next_steps("nonexistent-key") is False


def test_print_next_steps_unknown_key_silent(capsys) -> None:
    print_next_steps("definitely-not-a-key")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_print_next_steps_renders_registered_steps(capsys) -> None:
    print_next_steps("deploy-done")
    out = capsys.readouterr().out
    assert "cataforge doctor" in out
