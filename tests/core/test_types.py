"""Guards for the platform-agnostic type surface in ``core.types``."""

from __future__ import annotations

import cataforge.core.types as types


def test_permission_mode_enum_is_absent() -> None:
    """Permission modes are declared per-platform in profile.yaml
    ``permissions.modes``; no Python enum mirrors them. A reintroduced
    ``PermissionMode`` would be dead code whose snake_case values drift
    from the camelCase profile strings."""
    assert not hasattr(types, "PermissionMode")
