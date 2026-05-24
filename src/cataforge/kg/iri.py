"""CURIE / IRI helpers shared across kg/ modules.

Single source of truth for ``prefix:local → http://...`` expansion. Before
this module existed, the same logic lived in two places (``kg/store.py``
and ``kg/query.py``) with subtly different error types and blank-node
handling — refactors had to remember to update both. Centralising here
means consumers in ``kg/render``, ``kg/viz``, ``kg/adapters``, and
``kg/store_oxigraph`` all share one implementation.
"""

from __future__ import annotations

from cataforge.kg.ontology import NAMESPACES

# IRI schemes that already specify a full identifier and must NOT be
# treated as CURIEs even though they contain ``:``.
_PASSTHROUGH_SCHEMES = ("http://", "https://", "urn:")
# rdflib blank-node tokens (``_:foo``) are passed through untouched.
_BNODE_PREFIX = "_:"


class IRIExpansionError(ValueError):
    """Raised when a token can't be expanded to a full IRI.

    Subclasses ``ValueError`` so callers that already catch ``ValueError``
    (e.g. user-facing CLI commands wrapping query helpers) keep working.
    The dedicated subclass exists so ``kg/store.py`` can translate it to
    its module-specific ``StoreError`` without catching unrelated value
    errors raised elsewhere in the call stack.
    """


def expand_curie(token: str) -> str:
    """Expand a CURIE (``prefix:local``) to a full IRI.

    Pass through unchanged when *token*:

    * already starts with a recognised IRI scheme (``http://`` /
      ``https://`` / ``urn:``); or
    * is an rdflib blank-node token (``_:foo``).

    Raises :class:`IRIExpansionError` for bare tokens (no ``:``) and for
    unknown prefixes, so silent IRI coinage is impossible.
    """
    if token.startswith(_PASSTHROUGH_SCHEMES) or token.startswith(_BNODE_PREFIX):
        return token
    if ":" not in token:
        raise IRIExpansionError(
            f"bare token without prefix or scheme: {token!r}"
        )
    prefix, _, local = token.partition(":")
    base = NAMESPACES.get(prefix)
    if base is None:
        raise IRIExpansionError(
            f"unknown prefix {prefix!r} in {token!r}; register it in "
            "cataforge.kg.ontology before use."
        )
    return base + local
