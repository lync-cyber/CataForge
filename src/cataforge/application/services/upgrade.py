"""Upgrade service — CHANGELOG breaking-change detection for ``cataforge upgrade``.

Pure parsing logic (no Click, no IO beyond reading CHANGELOG.md): the
``upgrade check`` command renders these results. Keeping it here lets the
breaking-change scan be unit-tested without a CLI runner.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.core.version import parse_semver

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager

_CHANGELOG_HEADER_RE = re.compile(r"^## \[(?P<version>[^\]]+)\]")
_BREAKING_HEADER_RE = re.compile(r"^#{2,4}\s*(?:BREAKING|breaking)(?:\s|$)")

_DESIGN_TOOL_FIELD_RE = re.compile(r"(?m)^- 设计工具:\s*(\S+)")
_INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md")


def lift_design_tool_intent(cfg: ConfigManager) -> str | None:
    """Promote a penpot design-tool choice from the instruction file into framework.json.

    ``framework.json#project.design_tool`` is the single source of truth: deploy
    renders the instruction file's 设计工具 field from it and force-overwrites that
    field every run. A project that recorded penpot only in CLAUDE.md / AGENTS.md
    would have the choice silently cleared by the first such deploy, so before any
    deploy-bearing refresh (``upgrade apply`` or ``bootstrap``) we lift it into
    framework.json once. Idempotent — a no-op once design_tool is anything other
    than the default ``none``.
    """
    if cfg.design_tool != "none":
        return None
    for name in _INSTRUCTION_FILES:
        path = cfg.paths.root / name
        if not path.is_file():
            continue
        match = _DESIGN_TOOL_FIELD_RE.search(path.read_text())
        if match and match.group(1) == "penpot":
            cfg.set_design_tool("penpot")
            return "penpot"
    return None


def find_breaking_entries(
    scaffold_version: str,
    installed_version: str,
) -> list[tuple[str, str]]:
    """Scan CHANGELOG.md for BREAKING sections in the upgrade range.

    Returns ``(version, first_bullet)`` tuples for every section whose
    version sits between the scaffold's current state and the installed
    package, when that section contains a ``### BREAKING`` subheader.

    Silent on missing CHANGELOG or a malformed range — the check is a
    courtesy warning, not a correctness gate.
    """
    changelog = _find_changelog()
    if changelog is None:
        return []

    sections = _iter_changelog_sections(changelog.read_text())
    out: list[tuple[str, str]] = []
    for version, body in sections:
        if not _is_in_upgrade_range(version, scaffold_version, installed_version):
            continue
        summary = _extract_breaking_summary(body)
        if summary is not None:
            out.append((version, summary))
    return out


def _find_changelog() -> Path | None:
    """Walk up from cwd for a CHANGELOG.md (project root is where it lives)."""
    here = Path.cwd().resolve()
    for parent in (here, *here.parents):
        candidate = parent / "CHANGELOG.md"
        if candidate.is_file():
            return candidate
    return None


def _iter_changelog_sections(text: str) -> list[tuple[str, str]]:
    """Return ``(version, body)`` for every ``## [x.y.z]`` section."""
    sections: list[tuple[str, str]] = []
    current_version: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        header = _CHANGELOG_HEADER_RE.match(line)
        if header is not None:
            if current_version is not None:
                sections.append((current_version, "\n".join(current_body)))
            current_version = header.group("version")
            current_body = []
        elif current_version is not None:
            current_body.append(line)
    if current_version is not None:
        sections.append((current_version, "\n".join(current_body)))
    return sections


def _is_in_upgrade_range(version: str, lower: str, upper: str) -> bool:
    """True iff *lower < version <= upper* on semver ordering."""
    vv = parse_semver(version)
    lo = parse_semver(lower)
    hi = parse_semver(upper)
    if vv is None or lo is None or hi is None:
        return False
    return lo < vv <= hi


def _extract_breaking_summary(body: str) -> str | None:
    """Return the first non-blank line under a BREAKING subheader, or None."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if _BREAKING_HEADER_RE.match(line):
            for follow in lines[i + 1 :]:
                stripped = follow.strip().lstrip("-*").strip()
                if stripped:
                    return stripped
            return "(BREAKING section present; see CHANGELOG.md)"
    return None
