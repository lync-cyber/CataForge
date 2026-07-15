"""Shared messaging for CLI subcommands that are not implemented yet.

Stub commands raise :class:`NotImplementedFeature` (exit code 70,
BSD sysexits ``EX_SOFTWARE``) so that:

* CI scripts can reliably distinguish "feature not shipped yet" from
  Click's own usage errors (exit 2) and from generic failures (exit 1).
* The message prefix matches every other error the CLI emits
  (``Error: …`` on stderr).
"""

from __future__ import annotations

from cataforge.core.errors import EXIT_NOT_IMPLEMENTED

# Preserved as a public constant so tests and external tooling can import
# it without hard-coding the literal. Value is the exit code Click uses
# when :class:`NotImplementedFeature` propagates.
STUB_EXIT_CODE = EXIT_NOT_IMPLEMENTED

__all__ = ["STUB_EXIT_CODE"]
