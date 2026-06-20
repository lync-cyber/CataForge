"""B2 — cross-reference graph completeness.

Characterization tests for check_b2_cross_references. Covers:
- Happy path: all referenced skills resolve → no findings
- Missing skill referenced from agent → FAIL finding
- Missing skill referenced from skill depends → FAIL finding
- Orphan skill (not referenced by any agent or skill) → WARN finding
- Orphaned skill in ORPHAN_SKILL_WHITELIST → no finding
"""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.framework_review.framework_check import (
    Report,
    check_b2_cross_references,
    check_b2_suggested_tools,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_agent(tmp_path: Path, agent_id: str, skills: list[str]) -> None:
    """Write a minimal AGENT.md with a skills: frontmatter list."""
    agent_dir = tmp_path / ".cataforge" / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    skills_yaml = "".join(f"  - {s}\n" for s in skills)
    (agent_dir / "AGENT.md").write_text(
        f"---\nname: {agent_id}\ndescription: test\nskills:\n{skills_yaml}---\n"
        f"# {agent_id}\n## Identity\n- test\n",
        encoding="utf-8",
    )


def _write_skill(tmp_path: Path, skill_id: str, depends: list[str] | None = None) -> None:
    """Write a minimal SKILL.md with optional depends: frontmatter list."""
    skill_dir = tmp_path / ".cataforge" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    deps_yaml = ""
    if depends:
        deps_yaml = "depends:\n" + "".join(f"  - {d}\n" for d in depends)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: test\n{deps_yaml}---\n# {skill_id}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_b2_happy_path_no_findings(tmp_path: Path) -> None:
    """Agent references a skill that exists → no FAIL findings for that skill."""
    _write_agent(tmp_path, "product-manager", ["prd-writing"])
    _write_skill(tmp_path, "prd-writing")

    report = Report()
    check_b2_cross_references(tmp_path, report)

    # Filter to findings that mention the skills/agents we actually wrote.
    # SkillLoader may inject builtin skill names; we only assert on our fixtures.
    fail_findings = [
        f
        for f in report.findings
        if f.check_id == "B2_cross_reference_graph"
        and f.severity == "FAIL"
        and "prd-writing" in f.message
    ]
    assert fail_findings == [], f"unexpected FAIL: {[f.render() for f in fail_findings]}"


def test_b2_missing_skill_from_agent_fails(tmp_path: Path) -> None:
    """Agent references a skill that has no SKILL.md → FAIL finding."""
    _write_agent(tmp_path, "product-manager", ["nonexistent-skill"])
    # Do NOT create the skill.

    report = Report()
    check_b2_cross_references(tmp_path, report)

    fail_findings = [
        f
        for f in report.findings
        if f.check_id == "B2_cross_reference_graph" and f.severity == "FAIL"
    ]
    assert len(fail_findings) == 1
    assert "nonexistent-skill" in fail_findings[0].message
    assert "agents/product-manager" in fail_findings[0].location


def test_b2_missing_skill_from_depends_fails(tmp_path: Path) -> None:
    """Skill depends on a skill that has no SKILL.md → FAIL finding."""
    _write_skill(tmp_path, "my-skill", depends=["missing-dep"])
    # Do NOT create missing-dep.

    report = Report()
    check_b2_cross_references(tmp_path, report)

    fail_findings = [
        f
        for f in report.findings
        if f.check_id == "B2_cross_reference_graph" and f.severity == "FAIL"
    ]
    assert len(fail_findings) == 1
    assert "missing-dep" in fail_findings[0].message
    assert "skills/my-skill" in fail_findings[0].location


def test_b2_orphan_skill_warns(tmp_path: Path) -> None:
    """Skill not referenced by any agent or skill → WARN orphan finding."""
    _write_skill(tmp_path, "lonely-skill")
    # No agent references it.

    report = Report()
    check_b2_cross_references(tmp_path, report)

    warn_findings = [
        f
        for f in report.findings
        if f.check_id == "B2_cross_reference_graph"
        and f.severity == "WARN"
        and "lonely-skill" in f.location
    ]
    assert len(warn_findings) == 1
    assert "orphan" in warn_findings[0].message


def test_b2_whitelisted_orphan_skill_no_warning(tmp_path: Path) -> None:
    """Whitelisted skills are excluded from the orphan check."""
    # 'doc-review' is in ORPHAN_SKILL_WHITELIST
    _write_skill(tmp_path, "doc-review")

    report = Report()
    check_b2_cross_references(tmp_path, report)

    orphan_findings = [
        f
        for f in report.findings
        if f.check_id == "B2_cross_reference_graph" and "doc-review" in f.location
    ]
    assert orphan_findings == []


def test_b2_multiple_refs_to_same_missing_skill_each_ref_reported(tmp_path: Path) -> None:
    """Two agents referencing the same missing skill → one FAIL per referencing agent."""
    _write_agent(tmp_path, "agent-a", ["ghost-skill"])
    _write_agent(tmp_path, "agent-b", ["ghost-skill"])

    report = Report()
    check_b2_cross_references(tmp_path, report)

    fail_findings = [
        f
        for f in report.findings
        if f.check_id == "B2_cross_reference_graph" and f.severity == "FAIL"
    ]
    # Each referencing location produces its own FAIL finding.
    assert len(fail_findings) == 2
    locations = {f.location for f in fail_findings}
    assert "agents/agent-a" in locations
    assert "agents/agent-b" in locations


def test_b2_no_agents_no_skills_no_fail_findings(tmp_path: Path) -> None:
    """Empty project with no filesystem agents or skills → no FAIL findings.

    SkillLoader may still inject builtin skill ids; those may produce orphan
    WARNs.  This test only asserts that no FAIL findings are produced, which
    is the meaningful contract when the project has no cross-references at all.
    """
    report = Report()
    check_b2_cross_references(tmp_path, report)
    fail_findings = [f for f in report.findings if f.severity == "FAIL"]
    assert fail_findings == []


def test_b2_referenced_and_present_skill_no_fail_no_orphan_for_skill(tmp_path: Path) -> None:
    """Skill referenced by an agent and present → no FAIL and no orphan WARN for that skill."""
    _write_agent(tmp_path, "architect", ["doc-nav"])
    _write_skill(tmp_path, "doc-nav")

    report = Report()
    check_b2_cross_references(tmp_path, report)

    # Builtins may appear as orphans; assert only about our fixture skill.
    relevant = [
        f
        for f in report.findings
        if f.check_id == "B2_cross_reference_graph" and "doc-nav" in f.location
    ]
    assert relevant == []


# ---------------------------------------------------------------------------
# B2-β: suggested-tools capability_id validity
# ---------------------------------------------------------------------------


def _write_skill_with_tools(tmp_path: Path, skill_id: str, tools_csv: str) -> None:
    """Write a minimal SKILL.md with a suggested-tools frontmatter line."""
    skill_dir = tmp_path / ".cataforge" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: test\nsuggested-tools: {tools_csv}\n---\n"
        f"# {skill_id}\n",
        encoding="utf-8",
    )


def test_b2_suggested_tools_capability_ids_no_fail(tmp_path: Path) -> None:
    """All-capability_id suggested-tools → no B2_suggested_tools_valid FAIL."""
    _write_skill_with_tools(tmp_path, "my-skill", "file_read, shell_exec, agent_dispatch")

    report = Report()
    check_b2_suggested_tools(tmp_path, report)

    fails = [f for f in report.findings if f.check_id == "B2_suggested_tools_valid"]
    assert fails == [], [f.render() for f in fails]


def test_b2_suggested_tools_native_name_fails(tmp_path: Path) -> None:
    """A platform-native tool name (Read / Bash) → FAIL with the offending token."""
    _write_skill_with_tools(tmp_path, "my-skill", "Read, Glob, Bash")

    report = Report()
    check_b2_suggested_tools(tmp_path, report)

    fails = [f for f in report.findings if f.check_id == "B2_suggested_tools_valid"]
    offenders = {tok for f in fails for tok in ("Read", "Glob", "Bash") if tok in f.message}
    assert offenders == {"Read", "Glob", "Bash"}, [f.render() for f in fails]
    assert all("skills/my-skill" in f.location for f in fails)


def test_b2_suggested_tools_absent_field_no_fail(tmp_path: Path) -> None:
    """A skill with no suggested-tools field → no FAIL (field is optional)."""
    _write_skill(tmp_path, "no-tools-skill")

    report = Report()
    check_b2_suggested_tools(tmp_path, report)

    fails = [f for f in report.findings if f.check_id == "B2_suggested_tools_valid"]
    assert fails == []
