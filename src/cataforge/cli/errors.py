"""Unified CLI error types.

All user-facing error paths in the CLI layer should raise a subclass of
:class:`CataforgeError` rather than ``raise SystemExit(...)`` or
``click.secho(..., err=True)`` followed by a raw exit. Click renders these
as ``Error: <message>`` on stderr and applies the correct exit code, so:

* Output is consistent across commands (single ``Error:`` prefix).
* Exit codes are documented & non-magical (see :data:`EXIT_CODES`).
* Downstream scripts and CI can parse stderr uniformly.

Exit-code conventions (``docs/reference/cli.md`` §退出码):

* ``0``  — success
* ``1``  — generic failure (validation, business logic, missing prereq)
* ``2``  — reserved by Click for CLI usage errors (bad option, etc.)
* ``3``  — KG content verification gate failed (import verify, validate,
  export render, reconcile divergence) — distinguishes a failed *gate*
  from a generic failure so CI scripts can branch on it
* ``70`` — EX_SOFTWARE: feature not yet implemented (stub commands)
* ``75`` — EX_TEMPFAIL: transient issue (not currently used but reserved)

Do not introduce new exit codes without updating ``cli.md``.
"""

from __future__ import annotations

from pathlib import Path

import click

EXIT_GENERIC_FAILURE = 1
EXIT_KG_VERIFICATION_FAILED = 3
EXIT_QUERY_TIMEOUT = 6
EXIT_NOT_IMPLEMENTED = 70  # BSD sysexits.h EX_SOFTWARE


class CataforgeError(click.ClickException):
    """Base class for all CLI-surface errors.

    Subclasses only differ in ``exit_code`` and occasionally in how the
    message is composed. Raising this (instead of ``SystemExit``) lets
    Click print a consistent ``Error: <msg>`` line on stderr.
    """

    exit_code = EXIT_GENERIC_FAILURE


class NotInitializedError(CataforgeError):
    """Raised when a command requires ``.cataforge/`` but the project has none.

    The message directs the user at ``cataforge setup`` and, where known,
    includes the cwd that was searched so they can confirm they ran the
    command in the right place.
    """

    def __init__(self, root: Path, hint_platform: str = "claude-code") -> None:
        super().__init__(
            "No .cataforge/ scaffold found in this project.\n"
            f"  Project root: {root}\n"
            "  Run `cataforge setup` first to initialise the scaffold, e.g.:\n"
            f"    cataforge setup --platform {hint_platform}\n"
            "  See `cataforge --help` for the full command list."
        )


class ConfigError(CataforgeError):
    """Raised when a config file (framework.json, hooks.yaml, profile.yaml)
    is missing, malformed, or internally inconsistent."""


class ExternalToolError(CataforgeError):
    """Raised when a required external tool (docker, git, ruff, …) is
    missing, returns a non-zero exit, or emits unparseable output."""


class NotImplementedFeature(CataforgeError):  # noqa: N818 — public API since 0.1.0
    """Raised by stub subcommands that are on the roadmap but not yet
    functional. Exit code 70 (EX_SOFTWARE) distinguishes these from
    generic failures and from Click's own usage errors (exit 2)."""

    exit_code = EXIT_NOT_IMPLEMENTED


class KGError(CataforgeError):
    """Base class for ``cataforge kg`` subcommand errors.

    Two concrete subclasses split the kg error surface along the only
    axis that downstream scripts care about:

    * :class:`KGStoreError` — store unavailable (not initialised, already
      exists). Exit ``1`` like any other missing-prereq failure.
    * :class:`KGVerificationError` — a content gate (import verify,
      validate, export render, reconcile divergence) found drift. Exit
      ``3`` so CI can fail loudly *only* on real data issues, not on
      "you forgot to run ``kg init``" warm-up problems.

    Subclassing here (rather than mutating ``exit_code`` on a generic
    ``CataforgeError`` at every call site) keeps the per-subcommand
    contract declared in one place — call sites just pick the right
    subclass and ``exit_code`` follows automatically.
    """


class KGStoreError(KGError):
    """Raised when the KG store is in the wrong lifecycle state for the
    requested action (not initialised when one is needed, or already
    initialised when ``kg init`` was about to create one)."""

    exit_code = EXIT_GENERIC_FAILURE


class KGVerificationError(KGError):
    """Raised when a kg verification gate fails on the *content* of the
    graph: import-time triple verification, ``kg validate`` violations,
    ``kg export`` render errors, ``kg reconcile`` divergence between
    docs and the live store."""

    exit_code = EXIT_KG_VERIFICATION_FAILED


class KGQueryTimeoutError(KGError):
    """Raised when a SPARQL query exceeds the configured timeout."""

    exit_code = EXIT_QUERY_TIMEOUT


__all__ = [
    "CataforgeError",
    "ConfigError",
    "EXIT_GENERIC_FAILURE",
    "EXIT_KG_VERIFICATION_FAILED",
    "EXIT_NOT_IMPLEMENTED",
    "EXIT_QUERY_TIMEOUT",
    "ExternalToolError",
    "KGError",
    "KGQueryTimeoutError",
    "KGStoreError",
    "KGVerificationError",
    "NotImplementedFeature",
    "NotInitializedError",
]
