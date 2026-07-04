"""cataforge unattended build — CLI surface contracts."""

from __future__ import annotations

from cataforge.interface.cli.unattended_cmd import _OUTCOME_MESSAGE
from cataforge.runtime.unattended import (
    EXIT_CIRCUIT,
    EXIT_COMPLETE,
    EXIT_MAX_ITERATIONS,
    EXIT_PREFLIGHT,
)


def test_outcome_message_covers_every_exit_code() -> None:
    # Every exit code run_building_loop can return must have a human message —
    # a drift here would otherwise surface as a bare KeyError at runtime.
    assert set(_OUTCOME_MESSAGE) == {
        EXIT_COMPLETE,
        EXIT_CIRCUIT,
        EXIT_MAX_ITERATIONS,
        EXIT_PREFLIGHT,
    }
