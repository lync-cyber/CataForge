"""Next-step suggestions for cataforge CLI subcommands.

Single source of truth for "what should the user run next" hints. Subcommands
call ``print_next_steps("<key>")`` at the end of their happy paths; the keys
are stable so tests can assert on them.

To add a new key:

* Pick a kebab-case identifier that describes the *just-completed* state,
  not the next command (e.g. ``"deploy-done"`` not ``"run-doctor"``).
* Add the ``NextStep`` list below.
* Cite it from exactly one subcommand at end-of-success.

When a key has no follow-up (terminal command), use ``[]`` — the helper
silently no-ops, so subcommands don't need conditional branches.
"""

from __future__ import annotations

from cataforge.interface.cli._support.ui import NextStep, ui

NEXT_STEPS: dict[str, list[NextStep]] = {
    "setup-done": [
        NextStep("cataforge deploy", "render IDE artefacts (.claude/, CLAUDE.md)"),
        NextStep("cataforge bootstrap", "or run setup + deploy + doctor in one shot"),
    ],
    "setup-deployed": [
        NextStep("cataforge doctor", "verify the deployment is healthy"),
    ],
    "deploy-done": [
        NextStep("cataforge doctor", "verify deployment integrity"),
    ],
    "upgrade-checked-stale": [
        NextStep("cataforge upgrade apply", "apply the bundled scaffold"),
    ],
    "upgrade-applied": [
        NextStep("cataforge deploy", "re-render IDE artefacts against the fresh scaffold"),
        NextStep("cataforge doctor", "and run doctor to confirm nothing drifted"),
    ],
    "upgrade-up-to-date": [],
    "doctor-pass": [],
    # doctor-fail steps are populated dynamically by the doctor command,
    # since the right follow-up depends on which checks failed.
    "bootstrap-done": [],
    "sync-main-done": [
        NextStep("cataforge sync-main --prune", "delete merged feature branches"),
    ],
    "penpot-mcp-up": [
        NextStep(
            "open design.penpot.app",
            "load plugin manifest from http://localhost:4400/manifest.json",
        ),
    ],
}


def print_next_steps(key: str) -> None:
    """Render the registered next-step list for *key* (empty key → silent)."""
    ui.next_steps(NEXT_STEPS.get(key, []))


def has_next_steps(key: str) -> bool:
    return bool(NEXT_STEPS.get(key))
