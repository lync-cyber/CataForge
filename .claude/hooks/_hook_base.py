#!/usr/bin/env python3
"""CataForge Hook Infrastructure -- shared utilities for all hook scripts.

Provides:
- read_hook_input(): Unified stdin JSON reading with Windows UTF-8 handling
- hook_main(): Decorator that wraps hook entry points with error handling
"""

import json
import sys


def read_hook_input() -> dict:
    """Read and parse JSON from stdin with robust encoding handling.

    Uses sys.stdin.buffer (raw bytes) + explicit UTF-8 decode to avoid
    Windows cp936/cp1252 encoding issues that corrupt non-ASCII payloads.

    Returns:
        Parsed dict from stdin JSON. Empty dict on any parse error.
    """
    try:
        raw = sys.stdin.buffer.read()
        text = raw.decode("utf-8", errors="replace")
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, AttributeError):
        return {}


def hook_main(func):
    """Decorator for hook entry points.

    Wraps the function with:
    - Exception capture to stderr (never swallowed silently)
    - Guaranteed exit 0 (hooks should not block unless they explicitly exit 2)

    Usage::

        @hook_main
        def main():
            data = read_hook_input()
            # ... hook logic ...

        if __name__ == "__main__":
            main()
    """

    def wrapper():
        try:
            return func()
        except SystemExit:
            raise  # Allow explicit sys.exit() calls through
        except Exception as e:
            print(
                f"[HOOK-ERROR] {func.__module__}.{func.__name__}: {e}",
                file=sys.stderr,
            )
            sys.exit(0)

    return wrapper
