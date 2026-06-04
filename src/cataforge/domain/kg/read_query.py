"""Read-only SPARQL policy for the `kg query` CLI surface.

A single source for "is this SPARQL a safe read?" and "cap the result size".
"""

from __future__ import annotations

import re

from cataforge.core.errors import CataforgeError

SPARQL_WRITE_KEYWORDS = frozenset(
    ["UPDATE", "INSERT", "DELETE", "CLEAR", "DROP", "LOAD", "CREATE", "COPY", "MOVE", "ADD"]
)

_STRIP_RE = re.compile(
    r"(#[^\n]*\n|PREFIX\s+\S+\s*:\s*<[^>]*>\s*|BASE\s+<[^>]*>\s*)",
    re.IGNORECASE,
)


def first_sparql_keyword(sparql: str) -> str:
    """Return the first operative keyword of `sparql`, upper-cased.

    Leading comments and PREFIX / BASE declarations are stripped first so the
    real query form (SELECT / ASK / INSERT / …) is what gets classified.
    """
    stripped = _STRIP_RE.sub("", sparql).lstrip()
    tokens = stripped.split()
    return tokens[0].upper() if tokens else ""


def assert_read_only(sparql: str) -> None:
    """Raise `CataforgeError` when `sparql`'s leading keyword is a write op."""
    if first_sparql_keyword(sparql) in SPARQL_WRITE_KEYWORDS:
        raise CataforgeError(
            "SPARQL writes are not supported here — use 'kg add/update/delete' "
            "or a transaction script"
        )


def inject_limit(sparql: str, limit: int) -> str:
    """Append `LIMIT n` to a SELECT that lacks one; leave other forms untouched."""
    upper = sparql.upper()
    if "SELECT" in upper and "LIMIT" not in upper:
        return f"{sparql.rstrip().rstrip(';')} LIMIT {limit}"
    return sparql


__all__ = [
    "SPARQL_WRITE_KEYWORDS",
    "assert_read_only",
    "first_sparql_keyword",
    "inject_limit",
]
