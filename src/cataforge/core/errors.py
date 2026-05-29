"""Framework error hierarchy (SSOT).

All framework error paths raise a subclass of :class:`CataforgeError`.
These are pure exceptions carrying a documented ``exit_code`` and no
dependency on the CLI framework; :class:`cataforge.cli.errors.CataforgeGroup`
translates them into Click-rendered output at the command boundary
(``Error: <msg>`` on stderr with the matching exit code).

Exit-code conventions (``docs/reference/cli.md`` §退出码):

* ``0``  — success
* ``1``  — generic failure (validation, business logic, missing prereq)
* ``2``  — reserved by Click for CLI usage errors (bad option, etc.)
* ``3``  — KG content verification gate failed (import verify, validate,
  export render, reconcile divergence) — lets CI branch on a failed
  *gate* vs a generic failure
* ``6``  — SPARQL query exceeded the configured timeout
* ``70`` — EX_SOFTWARE: feature not yet implemented (stub commands)

Do not introduce new exit codes without updating ``cli.md``.
"""

from __future__ import annotations

from pathlib import Path

EXIT_GENERIC_FAILURE = 1
EXIT_KG_VERIFICATION_FAILED = 3
EXIT_QUERY_TIMEOUT = 6
EXIT_NOT_IMPLEMENTED = 70  # BSD sysexits.h EX_SOFTWARE


class CataforgeError(Exception):
    """Base class for all framework-surface errors.

    Subclasses differ only in ``exit_code``. The CLI boundary renders the
    string form as ``Error: <msg>`` on stderr with this exit code.
    """

    exit_code = EXIT_GENERIC_FAILURE


class NotInitializedError(CataforgeError):
    """Raised when a command requires ``.cataforge/`` but the project has none.

    The message directs the user at ``cataforge setup`` and includes the cwd
    that was searched so they can confirm they ran the command in the right
    place.
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
    functional. Exit code 70 (EX_SOFTWARE) distinguishes these from generic
    failures and from Click's own usage errors (exit 2)."""

    exit_code = EXIT_NOT_IMPLEMENTED


class KGCLIError(CataforgeError):
    """Base class for ``cataforge kg`` subcommand errors.

    Split along the only axis downstream scripts care about:
    :class:`KGStoreError` (store lifecycle, exit 1) vs
    :class:`KGVerificationError` (content gate, exit 3).
    """


class KGStoreError(KGCLIError):
    """Raised when the KG store is in the wrong lifecycle state for the
    requested action (not initialised when one is needed, or already
    initialised when ``kg init`` was about to create one)."""

    exit_code = EXIT_GENERIC_FAILURE


class KGVerificationError(KGCLIError):
    """Raised when a kg verification gate fails on graph *content*:
    import-time triple verification, ``kg validate`` violations,
    ``kg export`` render errors, ``kg reconcile`` divergence."""

    exit_code = EXIT_KG_VERIFICATION_FAILED


class KGQueryTimeoutError(KGCLIError):
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
    "KGCLIError",
    "KGQueryTimeoutError",
    "KGStoreError",
    "KGVerificationError",
    "NotImplementedFeature",
    "NotInitializedError",
]
