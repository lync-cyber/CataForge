"""The shared entity content-hash used by both authoring write paths."""

from __future__ import annotations

from cataforge.domain.kg._content_hash import entity_content_hash


def test_hash_is_content_sensitive_on_title() -> None:
    assert entity_content_hash("Login") != entity_content_hash("Logout")


def test_hash_is_content_sensitive_on_slots() -> None:
    base = entity_content_hash("Login", {})
    assert entity_content_hash("Login", {"priority": "high"}) != base


def test_hash_is_slot_order_independent() -> None:
    a = entity_content_hash("Login", {"priority": "high", "status": "open"})
    b = entity_content_hash("Login", {"status": "open", "priority": "high"})
    assert a == b


def test_hash_none_slots_equals_empty_slots() -> None:
    assert entity_content_hash("Login", None) == entity_content_hash("Login", {})


def test_both_write_paths_use_the_shared_helper() -> None:
    """Both authoring write paths derive the default hash from the shared
    helper, so a cross-path re-write of identical content stays idempotent."""
    import inspect

    from cataforge.application.context import write as cw
    from cataforge.interface.cli.kg import write as kg_write

    assert "entity_content_hash" in inspect.getsource(cw)
    assert "entity_content_hash" in inspect.getsource(kg_write)
