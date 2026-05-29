"""I/O helpers — UTF-8 by default, locale-independent.

Stdin: Python's text-mode ``sys.stdin`` decodes incoming bytes through the
platform locale (cp936 on a Chinese Windows install, cp1252 on Western
Windows, UTF-8 on most Linux). When a tool pipes UTF-8 bytes in (the heredoc
case from a shell, MCP/agent input, IDE hook payloads) this mismatch corrupts
multi-byte characters into either a hard ``UnicodeDecodeError`` or — under
``errors='surrogateescape'`` — silent ``\\udcXX`` surrogates that explode
later when re-encoded as UTF-8. Always read raw bytes from
``sys.stdin.buffer`` and decode them as UTF-8 yourself.

File reads: :func:`read_json` / :func:`read_yaml` centralize the
"read UTF-8 text, parse, raise a consistent :class:`ConfigError` with the
offending path on failure" pattern that was hand-rolled at ~30 call sites.
Use them wherever a *malformed or missing* config file should surface as a
clean error; best-effort readers that tolerate absence keep their own
``try/except ... return default`` because the raising contract does not fit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from cataforge.core.errors import ConfigError


def read_json(path: Path | str) -> Any:
    """Read and parse a UTF-8 JSON file, raising :class:`ConfigError` on
    a missing/unreadable file or malformed JSON (the path is in the message)."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read JSON file {p}: {e}") from e
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Malformed JSON in {p}: {e}") from e


def read_yaml(path: Path | str) -> Any:
    """Read and parse a UTF-8 YAML file, raising :class:`ConfigError` on
    a missing/unreadable file or malformed YAML.

    An empty document parses to ``{}`` (not ``None``) so callers can treat the
    result as a mapping without a None-guard — matching the prior ad-hoc
    ``yaml.safe_load(...) or {}`` idiom.
    """
    import yaml

    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read YAML file {p}: {e}") from e
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"Malformed YAML in {p}: {e}") from e
    return {} if data is None else data


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
