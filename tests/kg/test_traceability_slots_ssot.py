"""The traceability-slot tuple is a single shared constant.

`kg validate` (xref target-exists) and `kg drift-check` (dangling-relation
sweep) must enumerate the same object-property slots; a slot added for one
gate but not the other is a silent coverage hole. Both consumers bind the
one `_sparql_utils.TRACEABILITY_SLOTS`, so this guard fails if either
re-introduces a local copy.
"""

from __future__ import annotations

from cataforge.domain.kg import _sparql_utils, reconcile, validate


def test_reconcile_binds_shared_constant() -> None:
    assert reconcile.TRACEABILITY_SLOTS is _sparql_utils.TRACEABILITY_SLOTS


def test_validate_binds_shared_constant() -> None:
    assert validate.TRACEABILITY_SLOTS is _sparql_utils.TRACEABILITY_SLOTS


def test_slot_set_is_complete() -> None:
    assert set(_sparql_utils.TRACEABILITY_SLOTS) == {
        "implements",
        "satisfies",
        "verifies",
        "realizes",
        "delivers",
        "affects",
        "depends_on",
    }
