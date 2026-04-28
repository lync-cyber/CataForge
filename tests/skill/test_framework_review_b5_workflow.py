"""B5 — workflow coverage triple-hop matrix + EVENT-LOG cross-check.

Synthetic-project tests for the deepened B5 check_b5_workflow_coverage:

* B5_workflow_coverage_matrix (existing single-hop, still covered)
* B5_phase_skill_coverage (new: phase → agent → skill triple-hop)
* B5_eventlog_agent_return_drift (new: docs/EVENT-LOG.jsonl cross-check)
* B5_feature_phase_alignment (new: framework.json features ↔ Phase Routing)
"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.skill.builtins.framework_review.framework_check import (
    Report,
    check_b5_workflow_coverage,
)


def _write_orchestrator(tmp_path: Path, phase_routing: str) -> None:
    """Write an orchestrator AGENT.md with the given Phase Routing block."""
    orch_dir = tmp_path / ".cataforge" / "agents" / "orchestrator"
    orch_dir.mkdir(parents=True, exist_ok=True)
    (orch_dir / "AGENT.md").write_text(
        "---\nname: orchestrator\ndescription: test fixture\n---\n"
        "# orchestrator\n\n## Phase Routing\n"
        f"{phase_routing}\n",
        encoding="utf-8",
    )


def _write_agent(
    tmp_path: Path,
    agent_id: str,
    skills: list[str] | None = None,
) -> None:
    """Write a minimal AGENT.md for the given agent with optional skills:."""
    agent_dir = tmp_path / ".cataforge" / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    skills_yaml = ""
    if skills is not None:
        skills_yaml = "skills:\n" + "".join(f"  - {s}\n" for s in skills)
    (agent_dir / "AGENT.md").write_text(
        f"---\nname: {agent_id}\ndescription: test fixture\n{skills_yaml}---\n"
        f"# {agent_id}\n\n## Identity\n- test\n",
        encoding="utf-8",
    )


def _write_skill(tmp_path: Path, skill_id: str) -> None:
    skill_dir = tmp_path / ".cataforge" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: test fixture\n---\n"
        f"# {skill_id}\n",
        encoding="utf-8",
    )


def _write_event_log(tmp_path: Path, events: list[dict]) -> None:
    log_dir = tmp_path / "docs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / "EVENT-LOG.jsonl"
    log.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


def _write_framework_json(
    tmp_path: Path,
    features: dict | None = None,
    *,
    dispatcher_skills: list[str] | None = None,
    constants: dict | None = None,
) -> None:
    fw_dir = tmp_path / ".cataforge"
    fw_dir.mkdir(parents=True, exist_ok=True)
    payload: dict = {"version": "test"}
    if features is not None:
        payload["features"] = features
    if dispatcher_skills is not None:
        payload["dispatcher_skills"] = dispatcher_skills
    if constants is not None:
        payload["constants"] = constants
    (fw_dir / "framework.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# B5_phase_skill_coverage (triple-hop)
# ---------------------------------------------------------------------------


def test_b5_triple_hop_happy_path(tmp_path: Path) -> None:
    """Phase-routed agent with valid skills → no triple-hop findings."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["prd-writing", "doc-nav"])
    _write_skill(tmp_path, "prd-writing")
    _write_skill(tmp_path, "doc-nav")

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    triple_hop = [f for f in report.findings if f.check_id == "B5_phase_skill_coverage"]
    assert triple_hop == [], f"unexpected triple-hop findings: {[f.render() for f in triple_hop]}"


def test_b5_triple_hop_agent_with_no_skills_warns(tmp_path: Path) -> None:
    """Phase-routed agent declaring 0 skills → WARN."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=[])  # explicit empty list

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [
        f for f in report.findings
        if f.check_id == "B5_phase_skill_coverage" and "no skills:" in f.message
    ]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"
    assert "product-manager" in findings[0].message


def test_b5_triple_hop_dangling_skill_warns(tmp_path: Path) -> None:
    """Agent references a skill that doesn't exist → WARN."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["does-not-exist"])

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [
        f for f in report.findings
        if f.check_id == "B5_phase_skill_coverage" and "does-not-exist" in f.message
    ]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"


# ---------------------------------------------------------------------------
# B5_eventlog_agent_return_drift
# ---------------------------------------------------------------------------


def test_b5_eventlog_skipped_when_log_absent(tmp_path: Path) -> None:
    """No EVENT-LOG.jsonl → no eventlog findings (even with phase routing)."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_eventlog_agent_return_drift"]
    assert findings == []


def test_b5_eventlog_skipped_below_threshold(tmp_path: Path) -> None:
    """EVENT-LOG with <threshold returns → single INFO finding, no WARN."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_event_log(
        tmp_path,
        [
            {"ts": "2026-01-01T00:00:00Z", "event": "agent_return",
             "phase": "requirements", "agent": "architect",
             "ref": "docs/arch.md", "detail": "x"},
        ] * 5,
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_eventlog_agent_return_drift"]
    assert len(findings) == 1
    assert findings[0].severity == "INFO"
    assert "skipped" in findings[0].message


def test_b5_eventlog_threshold_overridable(tmp_path: Path) -> None:
    """constants.EVENT_LOG_DRIFT_MIN_EVENTS lowers/raises the activation bar."""
    _write_orchestrator(
        tmp_path,
        "Phase 1 requirements → product-manager → prd\n"
        "Phase 2 architecture → architect → arch",
    )
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_agent(tmp_path, "architect", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path, constants={"EVENT_LOG_DRIFT_MIN_EVENTS": 3}
    )
    # 3 returns all to architect → above threshold; product-manager has 0.
    _write_event_log(
        tmp_path,
        [
            {"ts": "2026-01-01T00:00:00Z", "event": "agent_return",
             "phase": "architecture", "agent": "architect",
             "ref": "docs/arch.md", "detail": "x"},
        ] * 3,
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    dead = [
        f for f in report.findings
        if f.check_id == "B5_eventlog_agent_return_drift"
        and "product-manager" in f.message
        and "0 agent_return" in f.message
    ]
    assert len(dead) == 1
    assert dead[0].severity == "WARN"


def test_b5_eventlog_dead_routing_warns(tmp_path: Path) -> None:
    """Phase-routed agent has 0 returns while log has ≥10 → WARN."""
    _write_orchestrator(
        tmp_path,
        "Phase 1 requirements → product-manager → prd\n"
        "Phase 2 architecture → architect → arch",
    )
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_agent(tmp_path, "architect", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    # 10 returns all attributed to architect, none to product-manager.
    _write_event_log(
        tmp_path,
        [
            {"ts": "2026-01-01T00:00:00Z", "event": "agent_return",
             "phase": "architecture", "agent": "architect",
             "ref": "docs/arch.md", "detail": "x"},
        ] * 10,
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    dead_findings = [
        f for f in report.findings
        if f.check_id == "B5_eventlog_agent_return_drift"
        and "product-manager" in f.message
        and "0 agent_return" in f.message
    ]
    assert len(dead_findings) == 1
    assert dead_findings[0].severity == "WARN"


def test_b5_eventlog_missing_ref_warns(tmp_path: Path) -> None:
    """Agent has returns but all lack `ref` field → WARN (output_path gap)."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_event_log(
        tmp_path,
        [
            {"ts": "2026-01-01T00:00:00Z", "event": "agent_return",
             "phase": "requirements", "agent": "product-manager",
             "detail": "x"},  # no ref field
        ] * 10,
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    no_ref = [
        f for f in report.findings
        if f.check_id == "B5_eventlog_agent_return_drift"
        and "lack" in f.message
        and "'ref'" in f.message
    ]
    assert len(no_ref) == 1


def test_b5_eventlog_tolerates_malformed_lines(tmp_path: Path) -> None:
    """Malformed JSONL lines → silently skipped, no exception."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")

    log_dir = tmp_path / "docs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "EVENT-LOG.jsonl").write_text(
        '{"event": "agent_return", "agent": "product-manager", '
        '"phase": "requirements", "ts": "2026-01-01T00:00:00Z", '
        '"ref": "x", "detail": "x"}\n'
        "garbage line that's not json\n"
        "{broken json\n"
        + "\n".join([
            '{"event": "agent_return", "agent": "product-manager", '
            '"phase": "requirements", "ts": "2026-01-01T00:00:00Z", '
            '"ref": "x", "detail": "x"}'
        ] * 9) + "\n",
        encoding="utf-8",
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    # 10 valid returns for product-manager, no dead-routing warning.
    dead = [
        f for f in report.findings
        if f.check_id == "B5_eventlog_agent_return_drift"
        and "product-manager" in f.message and "0 agent_return" in f.message
    ]
    assert dead == []


# ---------------------------------------------------------------------------
# B5_feature_phase_alignment
# ---------------------------------------------------------------------------


def test_b5_feature_phase_alignment_happy(tmp_path: Path) -> None:
    """All features.phase_guard hit known phases → no findings."""
    _write_orchestrator(
        tmp_path,
        "Phase 1 requirements → product-manager → prd\n"
        "Phase 5 development → tdd-engine → CODE",
    )
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        {
            "code-review": {"phase_guard": "development"},
            "doc-review": {"phase_guard": None},
        },
        dispatcher_skills=["tdd-engine"],
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_feature_phase_alignment"]
    assert findings == []


def test_b5_feature_phase_alignment_unknown_phase_warns(tmp_path: Path) -> None:
    """features.phase_guard refers to a phase not in routing → WARN."""
    _write_orchestrator(
        tmp_path,
        "Phase 1 requirements → product-manager → prd\n"
        "Phase 5 development → tdd-engine → CODE",
    )
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        {"ghost-feature": {"phase_guard": "phase_that_does_not_exist"}},
        dispatcher_skills=["tdd-engine"],
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [
        f for f in report.findings
        if f.check_id == "B5_feature_phase_alignment"
        and "ghost-feature" in f.location
    ]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"
    assert "phase_that_does_not_exist" in findings[0].message


def test_b5_feature_phase_alignment_null_guard_skipped(tmp_path: Path) -> None:
    """features with phase_guard=null are not validated (apply to all)."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(tmp_path, {
        "global-feat-1": {"phase_guard": None},
        "global-feat-2": {"phase_guard": None, "auto_enable": True},
    })

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_feature_phase_alignment"]
    assert findings == []
