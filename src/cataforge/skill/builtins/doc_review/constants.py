"""Shared constants for document validation."""

from __future__ import annotations

DOC_SPLIT_THRESHOLD_LINES = 300

VOLUME_TYPES = {
    "main",
    "features",
    "api",
    "data",
    "modules",
    "sprint",
    "components",
    "pages",
    "theme",
}

KNOWN_DOC_PREFIXES = {
    "prd",
    "arch",
    "dev-plan",
    "ui-spec",
    "test-report",
    "deploy-spec",
    "research-note",
    "changelog",
}
