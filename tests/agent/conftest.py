"""Shared fixtures for agent tests."""

from __future__ import annotations

import pytest

from cataforge.platform.registry import clear_cache


@pytest.fixture(autouse=True)
def _clear_adapter_cache() -> None:
    clear_cache()
