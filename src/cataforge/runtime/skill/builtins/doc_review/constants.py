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

# id prefixes a split volume owns. Continuity checks restrict to these so a
# cross-volume reference (an `api` volume citing E-005) is not mistaken for a
# missing local entity. Volumes absent here (e.g. `main`, `theme`) check every
# prefix of their doc_type.
VOLUME_OWNED_ID_PREFIXES = {
    "features": {"F", "AC"},
    "api": {"API"},
    "data": {"E"},
    "modules": {"M"},
    "sprint": {"T"},
    "components": {"UC"},
    "pages": {"P"},
}
