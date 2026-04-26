"""Stdin / stdout I/O helpers — UTF-8 by default, locale-independent.

Why this exists: Python's text-mode ``sys.stdin`` decodes incoming bytes
through the platform locale (cp936 on a Chinese Windows install, cp1252
on Western Windows, UTF-8 on most Linux). When a tool pipes UTF-8 bytes
in (the heredoc case from a shell, MCP/agent input, IDE hook payloads)
this mismatch corrupts multi-byte characters into either a hard
``UnicodeDecodeError`` or — under ``errors='surrogateescape'`` — silent
``\\udcXX`` surrogates that explode later when re-encoded as UTF-8.

Always read raw bytes from ``sys.stdin.buffer`` and decode them as UTF-8
yourself. This module wraps that pattern so call sites don't have to
remember.
"""

from __future__ import annotations

import sys


def read_stdin_utf8(errors: str = "strict") -> str:
    """Read all of stdin as UTF-8 text, ignoring the platform locale.

    *errors* mirrors :py:meth:`bytes.decode` — pass ``"strict"`` (default)
    for CLI commands where mojibake must surface as a clean failure, and
    ``"replace"`` for hook scripts that must keep running even when the
    upstream payload is broken.

    Use this anywhere you previously called ``sys.stdin.read()``. Use
    :func:`sys.stdin.buffer.read` directly only when you genuinely need
    raw bytes (e.g. binary protocols).
    """
    return sys.stdin.buffer.read().decode("utf-8", errors=errors)
