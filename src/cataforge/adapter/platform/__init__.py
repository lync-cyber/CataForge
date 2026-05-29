"""Platform adapters — isolate all IDE-specific logic."""

from __future__ import annotations

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.registry import detect_platform, get_adapter

__all__ = ["PlatformAdapter", "get_adapter", "detect_platform"]
