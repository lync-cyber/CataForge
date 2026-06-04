"""B8 — Anti-Patterns section presence + bullet floor + substantive content.

Characterization tests for check_b8_anti_pattern_floor. Covers:
- Missing section → WARN (B8_anti_pattern_section_present)
- Bullet count below floor → FAIL (B8_anti_pattern_floor)
- Placeholder-thin bullets (< 12 chars) → WARN (B8_anti_pattern_substantive)
- Sufficient bullets meeting floor → no findings
- Exempted skills/agents → no findings
- scope parameter routing (skills/agents/all)
- floor overridable via framework.json constants
"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.runtime.skill.builtins.framework_review.framework_check import (
    Report,
    check_b8_anti_pattern_floor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill(tmp_path: Path, skill_id: str, body: str) -> None:
    """Write a SKILL.md with the given body (after frontmatter)."""
    skill_dir = tmp_path / ".cataforge" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: test\n---\n# {skill_id}\n\n{body}\n",
        encoding="utf-8",
    )


def _write_agent(tmp_path: Path, agent_id: str, body: str) -> None:
    """Write an AGENT.md with the given body (after frontmatter)."""
    agent_dir = tmp_path / ".cataforge" / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "AGENT.md").write_text(
        f"---\nname: {agent_id}\ndescription: test\n---\n# {agent_id}\n\n{body}\n",
        encoding="utf-8",
    )


def _write_framework_json(
    tmp_path: Path,
    skill_floor: int | None = None,
    agent_floor: int | None = None,
) -> None:
    """Write .cataforge/framework.json with optional floor constants."""
    fw_dir = tmp_path / ".cataforge"
    fw_dir.mkdir(parents=True, exist_ok=True)
    consts: dict = {}
    if skill_floor is not None:
        consts["ANTI_PATTERN_MIN_COUNT_SKILL"] = skill_floor
    if agent_floor is not None:
        consts["ANTI_PATTERN_MIN_COUNT_AGENT"] = agent_floor
    (fw_dir / "framework.json").write_text(
        json.dumps({"version": "test", "constants": consts}),
        encoding="utf-8",
    )


def _good_bullets(count: int) -> str:
    """Generate *count* substantive Anti-Pattern bullets (>= 12 chars each)."""
    return "\n".join(f"- 禁止: 不当操作示例 {i} — 应改为正确用法" for i in range(1, count + 1))


# ---------------------------------------------------------------------------
# B8_anti_pattern_section_present
# ---------------------------------------------------------------------------


def test_b8_missing_section_warns(tmp_path: Path) -> None:
    """Skill without ## Anti-Patterns section → WARN."""
    _write_skill(tmp_path, "my-skill", "## 能力边界\n- test\n")

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_section_present"]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"
    assert "my-skill" in findings[0].location


def test_b8_missing_agent_section_warns(tmp_path: Path) -> None:
    """Agent without ## Anti-Patterns section → WARN."""
    _write_agent(tmp_path, "my-agent", "## Identity\n- test\n")

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "agents", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_section_present"]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"
    assert "my-agent" in findings[0].location


# ---------------------------------------------------------------------------
# B8_anti_pattern_floor
# ---------------------------------------------------------------------------


def test_b8_bullet_count_below_skill_floor_fails(tmp_path: Path) -> None:
    """Skill with fewer bullets than the floor → FAIL."""
    # Default floor for SKILL is 3; provide only 2 substantive bullets.
    body = "## Anti-Patterns\n" + _good_bullets(2)
    _write_skill(tmp_path, "my-skill", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_floor"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "my-skill" in findings[0].location
    assert "2" in findings[0].message


def test_b8_bullet_count_below_agent_floor_fails(tmp_path: Path) -> None:
    """Agent with fewer bullets than the floor → FAIL."""
    # Default floor for AGENT is 4; provide only 3 substantive bullets.
    body = "## Anti-Patterns\n" + _good_bullets(3)
    _write_agent(tmp_path, "my-agent", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "agents", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_floor"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "4" in findings[0].message  # minimum stated in message


def test_b8_bullet_count_at_skill_floor_passes(tmp_path: Path) -> None:
    """Skill with exactly the floor bullet count → no floor finding."""
    body = "## Anti-Patterns\n" + _good_bullets(3)
    _write_skill(tmp_path, "my-skill", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_floor"]
    assert findings == []


def test_b8_bullet_count_at_agent_floor_passes(tmp_path: Path) -> None:
    """Agent with exactly the floor bullet count → no floor finding."""
    body = "## Anti-Patterns\n" + _good_bullets(4)
    _write_agent(tmp_path, "my-agent", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "agents", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_floor"]
    assert findings == []


# ---------------------------------------------------------------------------
# B8_anti_pattern_substantive
# ---------------------------------------------------------------------------


def test_b8_thin_bullets_warn(tmp_path: Path) -> None:
    """Bullets with < 12 visible chars → WARN with count and first example."""
    # Provide 3 bullets meeting the floor, but one is thin.
    body = (
        "## Anti-Patterns\n"
        "- 禁止: 短\n"  # thin (< 12 chars body)
        "- 禁止: 不当操作示例一 — 应改为正确用法\n"
        "- 禁止: 不当操作示例二 — 应改为正确用法\n"
    )
    _write_skill(tmp_path, "my-skill", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_substantive"]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"
    assert "1" in findings[0].message  # 1 thin bullet


def test_b8_no_thin_bullets_no_substantive_warning(tmp_path: Path) -> None:
    """All bullets substantive (≥ 12 chars) → no substantive warning."""
    body = "## Anti-Patterns\n" + _good_bullets(3)
    _write_skill(tmp_path, "my-skill", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_substantive"]
    assert findings == []


# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------


def test_b8_exempt_skill_skipped(tmp_path: Path) -> None:
    """Exempt skills (e.g. tdd-engine) are not checked."""
    _write_skill(tmp_path, "tdd-engine", "## Some Section\n- test\n")

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    findings = [f for f in report.findings if "tdd-engine" in f.location]
    assert findings == []


def test_b8_exempt_agent_skipped(tmp_path: Path) -> None:
    """Exempt agents (e.g. orchestrator) are not checked."""
    _write_agent(tmp_path, "orchestrator", "## Identity\n- test\n")

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "agents", report)

    findings = [f for f in report.findings if "orchestrator" in f.location]
    assert findings == []


# ---------------------------------------------------------------------------
# Scope parameter routing
# ---------------------------------------------------------------------------


def test_b8_scope_skills_skips_agents(tmp_path: Path) -> None:
    """scope=skills only checks skills, not agents."""
    _write_agent(tmp_path, "my-agent", "## Identity\n- test\n")  # no Anti-Patterns
    _write_skill(tmp_path, "my-skill", "## Anti-Patterns\n" + _good_bullets(3))

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    agent_findings = [f for f in report.findings if "my-agent" in f.location]
    assert agent_findings == []


def test_b8_scope_agents_skips_skills(tmp_path: Path) -> None:
    """scope=agents only checks agents, not skills."""
    _write_skill(tmp_path, "my-skill", "## Identity\n- test\n")  # no Anti-Patterns
    _write_agent(tmp_path, "my-agent", "## Anti-Patterns\n" + _good_bullets(4))

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "agents", report)

    skill_findings = [f for f in report.findings if "my-skill" in f.location]
    assert skill_findings == []


def test_b8_scope_all_checks_both(tmp_path: Path) -> None:
    """scope=all reports issues from both skills and agents."""
    _write_skill(tmp_path, "my-skill", "## Identity\n- test\n")  # missing Anti-Patterns
    _write_agent(tmp_path, "my-agent", "## Identity\n- test\n")  # missing Anti-Patterns

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "all", report)

    skill_findings = [f for f in report.findings if "my-skill" in f.location]
    agent_findings = [f for f in report.findings if "my-agent" in f.location]
    assert len(skill_findings) >= 1
    assert len(agent_findings) >= 1


# ---------------------------------------------------------------------------
# Floor override via framework.json
# ---------------------------------------------------------------------------


def test_b8_custom_skill_floor_from_framework_json(tmp_path: Path) -> None:
    """Custom ANTI_PATTERN_MIN_COUNT_SKILL=5 from framework.json applies."""
    _write_framework_json(tmp_path, skill_floor=5)
    # 3 bullets meets default floor (3) but not custom floor (5).
    body = "## Anti-Patterns\n" + _good_bullets(3)
    _write_skill(tmp_path, "my-skill", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_floor"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "5" in findings[0].message


def test_b8_custom_agent_floor_from_framework_json(tmp_path: Path) -> None:
    """Custom ANTI_PATTERN_MIN_COUNT_AGENT=2 from framework.json lowers the bar."""
    _write_framework_json(tmp_path, agent_floor=2)
    # 2 bullets meets the lowered custom floor → no floor finding.
    body = "## Anti-Patterns\n" + _good_bullets(2)
    _write_agent(tmp_path, "my-agent", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "agents", report)

    findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_floor"]
    assert findings == []


# ---------------------------------------------------------------------------
# Anti-Patterns section boundary detection
# ---------------------------------------------------------------------------


def test_b8_bullets_after_next_heading_not_counted(tmp_path: Path) -> None:
    """Bullets in the section after ## Anti-Patterns are not counted."""
    body = (
        "## Anti-Patterns\n"
        "- 禁止: 不当操作示例一 — 应改为正确用法\n"  # 1 bullet under Anti-Patterns
        "\n"
        "## Next Section\n"
        "- 禁止: 不当操作示例二 — 应改为正确用法\n"
        "- 禁止: 不当操作示例三 — 应改为正确用法\n"
    )
    _write_skill(tmp_path, "my-skill", body)

    report = Report()
    check_b8_anti_pattern_floor(tmp_path, "skills", report)

    floor_findings = [f for f in report.findings if f.check_id == "B8_anti_pattern_floor"]
    # Only 1 bullet counted under Anti-Patterns → below floor of 3 → FAIL
    assert len(floor_findings) == 1
    assert "1" in floor_findings[0].message
