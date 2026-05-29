"""Semver parsing (SSOT).

Only the *parse* is shared here. Comparison policy differs by call site
(strict ``>=`` gate, ``lower < v <= upper`` upgrade range, placeholder-aware
"newer" check, suffix tiebreaker for issue-version detection) and stays at
those sites, composed on top of :func:`parse_semver`.
"""

from __future__ import annotations

import re

_SEMVER_PREFIX_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def parse_semver(version: str) -> tuple[int, int, int] | None:
    """Return leading ``MAJOR.MINOR.PATCH`` as an int tuple, or ``None`` when
    the string does not start with a dotted-numeric triple.

    Any suffix after patch (``-rc1``, ``rc1``, build metadata) is ignored. The
    caller is responsible for stripping a leading ``v`` if its inputs carry one.
    """
    m = _SEMVER_PREFIX_RE.match(version)
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


__all__ = ["parse_semver"]
