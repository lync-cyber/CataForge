"""ask() chokepoint forces QueryBoolean → bool (spike-2 §2.2, issue #142).

The crux of issue #142 §2.2: `store.query(ask_sparql) == True` silently
always evaluates False because pyoxigraph 0.5.x returns its own
`QueryBoolean` type. The `ask()` utility wraps the result through `bool()`
so callers receive a real Python `bool`. These tests pin that contract.
"""

from __future__ import annotations

import pytest


def _empty_store():
    import pyoxigraph as ox

    return ox.Store()


def _store_with_one_triple():
    import pyoxigraph as ox

    s = ox.Store()
    s.add(
        ox.Quad(
            ox.NamedNode("https://ex.org/a"),
            ox.NamedNode("https://ex.org/p"),
            ox.NamedNode("https://ex.org/b"),
        )
    )
    return s


def test_returns_real_python_bool_false() -> None:
    from cataforge.domain.kg import ask

    result = ask(_empty_store(), "ASK { ?s ?p ?o }")
    assert result is False
    assert isinstance(result, bool)


def test_returns_real_python_bool_true() -> None:
    from cataforge.domain.kg import ask

    result = ask(_store_with_one_triple(), "ASK { ?s ?p ?o }")
    assert result is True
    assert isinstance(result, bool)


def test_documents_the_antipattern_in_a_pin() -> None:
    """If pyoxigraph ever changes Store.query() to return a real bool, the
    `ask()` wrapper becomes a no-op and this issue's `_ask.py` should be
    removed. This test fails loudly when that condition arrives so we
    notice."""
    import pyoxigraph as ox

    raw = ox.Store().query("ASK { ?s ?p ?o }")
    assert not isinstance(raw, bool), (
        "pyoxigraph.Store.query() now returns a real bool; the ask() "
        "chokepoint in cataforge.domain.kg._ask is no longer load-bearing — "
        "consider removing it and the pre-commit grep gate."
    )


def test_rejects_non_ask_query() -> None:
    from cataforge.domain.kg import ask

    with pytest.raises(ValueError):
        ask(_empty_store(), "SELECT ?s WHERE { ?s ?p ?o }")
