"""Shared helpers for SPARQL string handling and result reading.

Two responsibilities:

1. **Reading** pyoxigraph ``QuerySolution`` rows (``_row_lookup`` / ``_term_value`` /
   ``_strv``) — used by every query-shaped module to defensively extract
   variable bindings whether or not the binding exists.

2. **Escaping** user-controlled input before it is interpolated into SPARQL
   text. ``escape_sparql_literal`` produces a body suitable for the inside
   of ``"..."`` literals (caller adds the quotes); ``escape_iri_component``
   percent-encodes a single path segment for safe interpolation between
   ``<`` and ``>``; ``assert_safe_iri`` raises on already-formed IRIs that
   would break the angle-bracket boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from cataforge.kg._config import KGConfig

# SPARQL 1.1 STRING_LITERAL ECHAR set: \t, \b, \n, \r, \f, \", \', \\
# Single-character escape table; other C0 controls are emitted as \uXXXX.
_SPARQL_ECHAR: dict[str, str] = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}

# Characters that, if present in an IRI, would break the ``<...>`` boundary
# or violate RFC 3987 IRI productions for the part after the scheme.
_IRI_FORBIDDEN_CHARS: frozenset[str] = frozenset('<>"{}|^`\\ ')

# Safe characters retained verbatim in entity-id IRI segments: the
# unreserved set from RFC 3986 plus ``/`` for path separators that
# callers may already include.
_IRI_SAFE_SEGMENT = "-._~/"


def _term_value(term: Any) -> Any:
    if term is None:
        return None
    return getattr(term, "value", term)


def _row_lookup(row: Any, var: str) -> Any:
    """Read ``row[var]`` from a pyoxigraph ``QuerySolution`` (or a dict).

    Returns ``None`` both when the variable is unbound and when the
    variable name is not part of the projection.
    """
    try:
        return row[var]
    except (KeyError, IndexError):
        return None


def _strv(term: Any) -> str | None:
    v = _term_value(term)
    return None if v is None else str(v)


def escape_sparql_literal(value: str) -> str:
    """Escape a Python string so it is safe inside a SPARQL ``"..."`` literal.

    The caller is responsible for the surrounding double quotes. This
    function handles the literal *body* only.

    Escapes ``\\``, ``"``, common whitespace control characters
    (``\\t \\n \\r \\b \\f``), and emits remaining C0 controls
    (``U+0000`` – ``U+001F`` minus the escape table) as ``\\uXXXX``.
    Higher-plane characters and Unicode supplementary code points pass
    through verbatim — SPARQL 1.1 string literals accept them.

    Raises:
        TypeError: if ``value`` is not ``str``.
    """
    if not isinstance(value, str):
        raise TypeError(f"escape_sparql_literal expects str, got {type(value).__name__}")
    out: list[str] = []
    for ch in value:
        esc = _SPARQL_ECHAR.get(ch)
        if esc is not None:
            out.append(esc)
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return "".join(out)


def escape_iri_component(segment: str) -> str:
    """Percent-encode a path segment so it is safe between ``<`` and ``>``.

    Use this for user-controlled values (entity_id, class_name, project_id)
    that are concatenated into an IRI. Reserved IRI delimiters and
    whitespace become ``%XX``; the RFC 3986 unreserved set plus ``/`` is
    preserved verbatim so already-formed path segments survive intact.

    Raises:
        TypeError: if ``segment`` is not ``str``.
    """
    if not isinstance(segment, str):
        raise TypeError(f"escape_iri_component expects str, got {type(segment).__name__}")
    return quote(segment, safe=_IRI_SAFE_SEGMENT)


def assert_safe_iri(iri: str) -> str:
    """Validate an already-formed IRI before angle-bracket interpolation.

    Returns the IRI unchanged on success. Raises ``ValueError`` if the
    IRI contains any character that would break ``<{iri}>`` boundary in
    SPARQL or violate RFC 3987 IRI productions (``<``, ``>``, ``"``,
    ``{``, ``}``, ``|``, ``^``, `` ` ``, ``\\``, whitespace, or any C0
    control).

    Use this on values that should already be percent-encoded (e.g.
    output of ``entity_iri()``) before splicing into SPARQL strings.
    """
    if not isinstance(iri, str):
        raise TypeError(f"assert_safe_iri expects str, got {type(iri).__name__}")
    for ch in iri:
        if ch in _IRI_FORBIDDEN_CHARS or ord(ch) < 0x21:
            raise ValueError(f"IRI contains forbidden character {ch!r} (U+{ord(ch):04X}): {iri!r}")
    return iri


def cf_namespace(config: KGConfig) -> str:
    """Canonical cf: prefix value — trailing-slash-normalised ontology namespace."""
    return config.ontology_namespace.rstrip("/") + "/"


__all__ = [
    "_row_lookup",
    "_strv",
    "_term_value",
    "assert_safe_iri",
    "cf_namespace",
    "escape_iri_component",
    "escape_sparql_literal",
]
