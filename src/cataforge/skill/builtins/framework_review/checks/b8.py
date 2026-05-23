"""B8 — Anti-Patterns section presence + bullet floor + substantive content."""

from __future__ import annotations

import re
from pathlib import Path

from .._constants import (
    B1_REQUIRED_SECTIONS_EXEMPT_AGENTS,
    B1_REQUIRED_SECTIONS_EXEMPT_SKILLS,
)
from .._discover import discover_agents, discover_skills
from .._framework_data import read_anti_pattern_floor
from .._types import Report

_ANTI_PATTERN_HEADING_RE = re.compile(r"^##\s+Anti-?Patterns\s*$", re.MULTILINE)


def _extract_anti_patterns(text: str) -> tuple[bool, list[str]] | None:
    """Locate the ``## Anti-Patterns`` section and return its bullet list.

    Returns ``None`` if no section header is found.  The first tuple element
    indicates whether the section exists; the second is the list of
    bullet-line bodies (excluding the leading ``- ``).
    """
    m = _ANTI_PATTERN_HEADING_RE.search(text)
    if m is None:
        return None
    start = m.end()
    rest = text[start:]
    end_match = re.search(r"^##\s+", rest, re.MULTILINE)
    body = rest if end_match is None else rest[: end_match.start()]
    bullets: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "+ ")):
            bullets.append(stripped[2:].strip())
    return True, bullets


def check_b8_anti_pattern_floor(root: Path, scope: str, report: Report) -> None:
    """B8: Anti-Patterns section presence + bullet floor + substantive bullets.

    Three sub-checks:

    * ``B8_anti_pattern_section_present`` (α) — every non-exempt skill /
      agent should have a ``## Anti-Patterns`` section. WARN on missing.
    * ``B8_anti_pattern_floor`` (β) — bullet count must meet
      ``constants.ANTI_PATTERN_MIN_COUNT_SKILL`` (default 3) for skills
      and ``ANTI_PATTERN_MIN_COUNT_AGENT`` (default 4) for agents.
      Insufficient counts FAIL.
    * ``B8_anti_pattern_substantive`` (γ) — each bullet must be ≥ 12
      visible characters of body text (filters placeholder stubs).
      Sub-threshold bullets WARN per file.

    Skills / agents in the same exemption sets used by B1 are skipped:
    runtime adapters and macro skills legitimately don't have a
    standalone Anti-Patterns section.
    """
    skill_floor = read_anti_pattern_floor(root, "SKILL")
    agent_floor = read_anti_pattern_floor(root, "AGENT")

    targets: list[tuple[str, Path, str, int]] = []
    if scope in ("skills", "all"):
        for sid, path in discover_skills(root).items():
            if sid in B1_REQUIRED_SECTIONS_EXEMPT_SKILLS:
                continue
            targets.append((f"skills/{sid}", path, "skill", skill_floor))
    if scope in ("agents", "all"):
        for aid, path in discover_agents(root).items():
            if aid in B1_REQUIRED_SECTIONS_EXEMPT_AGENTS:
                continue
            targets.append((f"agents/{aid}", path, "agent", agent_floor))

    for label, path, kind, floor in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        result = _extract_anti_patterns(text)
        if result is None:
            report.add(
                "B8_anti_pattern_section_present",
                "WARN",
                label,
                f"{kind} missing '## Anti-Patterns' section "
                f"(B1 entry-section synonym does not substitute)",
            )
            continue
        _, bullets = result
        if len(bullets) < floor:
            report.add(
                "B8_anti_pattern_floor",
                "FAIL",
                label,
                f"{kind} '## Anti-Patterns' has {len(bullets)} bullet(s); "
                f"minimum is {floor} "
                f"(constants.ANTI_PATTERN_MIN_COUNT_{kind.upper()})",
            )
        # 12 chars = "禁止: 修改测试文件" length.
        thin = [b for b in bullets if len(b) < 12]
        if thin:
            report.add(
                "B8_anti_pattern_substantive",
                "WARN",
                label,
                f"{kind} has {len(thin)} placeholder-thin Anti-Pattern "
                f"bullet(s) (< 12 chars body); first: "
                f"{thin[0]!r}",
            )
