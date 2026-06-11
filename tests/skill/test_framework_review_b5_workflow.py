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

from cataforge.runtime.skill.builtins.framework_review.framework_check import (
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
        f"---\nname: {skill_id}\ndescription: test fixture\n---\n# {skill_id}\n",
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
    workflow: dict | None = None,
    platform: str | None = None,
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
    if workflow is not None:
        payload["workflow"] = workflow
    if platform is not None:
        payload["runtime"] = {"platform": platform}
    (fw_dir / "framework.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _write_platform_profile(tmp_path: Path, platform: str, *, subagent_interactive: bool) -> None:
    """Write a minimal platform profile.yaml with the subagent_interactive flag."""
    prof_dir = tmp_path / ".cataforge" / "platforms" / platform
    prof_dir.mkdir(parents=True, exist_ok=True)
    (prof_dir / "profile.yaml").write_text(
        f"platform_id: {platform}\nfeatures:\n"
        f"  subagent_interactive: {'true' if subagent_interactive else 'false'}\n",
        encoding="utf-8",
    )


def _workflow(phases: list[dict], mode: str = "standard") -> dict:
    """Build a ``framework.json#/workflow`` payload from phase dicts."""
    return {"modes": {mode: {"phases": phases}}}


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
        f
        for f in report.findings
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
        f
        for f in report.findings
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
            {
                "ts": "2026-01-01T00:00:00Z",
                "event": "agent_return",
                "phase": "requirements",
                "agent": "architect",
                "ref": "docs/arch.md",
                "detail": "x",
            },
        ]
        * 5,
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
        "Phase 1 requirements → product-manager → prd\nPhase 2 architecture → architect → arch",
    )
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_agent(tmp_path, "architect", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(tmp_path, constants={"EVENT_LOG_DRIFT_MIN_EVENTS": 3})
    # 3 returns all to architect → above threshold; product-manager has 0.
    _write_event_log(
        tmp_path,
        [
            {
                "ts": "2026-01-01T00:00:00Z",
                "event": "agent_return",
                "phase": "architecture",
                "agent": "architect",
                "ref": "docs/arch.md",
                "detail": "x",
            },
        ]
        * 3,
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    dead = [
        f
        for f in report.findings
        if f.check_id == "B5_eventlog_agent_return_drift"
        and "product-manager" in f.message
        and "0 agent_return" in f.message
    ]
    assert len(dead) == 1
    assert dead[0].severity == "FAIL"


def test_b5_eventlog_dead_routing_warns(tmp_path: Path) -> None:
    """Phase-routed agent has 0 returns while log has ≥10 → FAIL (post-F-010)."""
    _write_orchestrator(
        tmp_path,
        "Phase 1 requirements → product-manager → prd\nPhase 2 architecture → architect → arch",
    )
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_agent(tmp_path, "architect", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    # 10 returns all attributed to architect, none to product-manager.
    _write_event_log(
        tmp_path,
        [
            {
                "ts": "2026-01-01T00:00:00Z",
                "event": "agent_return",
                "phase": "architecture",
                "agent": "architect",
                "ref": "docs/arch.md",
                "detail": "x",
            },
        ]
        * 10,
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    dead_findings = [
        f
        for f in report.findings
        if f.check_id == "B5_eventlog_agent_return_drift"
        and "product-manager" in f.message
        and "0 agent_return" in f.message
    ]
    assert len(dead_findings) == 1
    assert dead_findings[0].severity == "FAIL"


def test_b5_eventlog_missing_ref_warns(tmp_path: Path) -> None:
    """Agent has returns but all lack `ref` field → WARN (output_path gap)."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_event_log(
        tmp_path,
        [
            {
                "ts": "2026-01-01T00:00:00Z",
                "event": "agent_return",
                "phase": "requirements",
                "agent": "product-manager",
                "detail": "x",
            },  # no ref field
        ]
        * 10,
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    no_ref = [
        f
        for f in report.findings
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
        + "\n".join(
            [
                '{"event": "agent_return", "agent": "product-manager", '
                '"phase": "requirements", "ts": "2026-01-01T00:00:00Z", '
                '"ref": "x", "detail": "x"}'
            ]
            * 9
        )
        + "\n",
        encoding="utf-8",
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    # 10 valid returns for product-manager, no dead-routing warning.
    dead = [
        f
        for f in report.findings
        if f.check_id == "B5_eventlog_agent_return_drift"
        and "product-manager" in f.message
        and "0 agent_return" in f.message
    ]
    assert dead == []


# ---------------------------------------------------------------------------
# B5_feature_phase_alignment
# ---------------------------------------------------------------------------


def test_b5_feature_phase_alignment_happy(tmp_path: Path) -> None:
    """All features.phase_guard hit known phases → no findings."""
    _write_orchestrator(
        tmp_path,
        "Phase 1 requirements → product-manager → prd\nPhase 5 development → tdd-engine → CODE",
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
        "Phase 1 requirements → product-manager → prd\nPhase 5 development → tdd-engine → CODE",
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
        f
        for f in report.findings
        if f.check_id == "B5_feature_phase_alignment" and "ghost-feature" in f.location
    ]
    assert len(findings) == 1
    assert findings[0].severity == "WARN"
    assert "phase_that_does_not_exist" in findings[0].message


def test_b5_feature_phase_alignment_null_guard_skipped(tmp_path: Path) -> None:
    """features with phase_guard=null are not validated (apply to all)."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        {
            "global-feat-1": {"phase_guard": None},
            "global-feat-2": {"phase_guard": None, "auto_enable": True},
        },
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_feature_phase_alignment"]
    assert findings == []


# ---------------------------------------------------------------------------
# B5_interactive_host (B5-ζ: interactive phase must run inline)
# ---------------------------------------------------------------------------


def test_b5_interactive_host_inline_passes(tmp_path: Path) -> None:
    """interactive phase with execution_host=inline → no findings."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        workflow=_workflow(
            [
                {
                    "phase": "requirements",
                    "role": "product-manager",
                    "execution_host": "inline",
                    "interactive": True,
                }
            ]
        ),
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    assert [f for f in report.findings if f.check_id == "B5_interactive_host"] == []


def test_b5_interactive_host_subagent_fails(tmp_path: Path) -> None:
    """interactive phase dispatched as subagent without ack → FAIL."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        workflow=_workflow(
            [
                {
                    "phase": "requirements",
                    "role": "product-manager",
                    "execution_host": "subagent",
                    "interactive": True,
                }
            ]
        ),
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_interactive_host"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "requirements" in findings[0].message


def test_b5_interactive_host_ack_downgrades_to_info(tmp_path: Path) -> None:
    """interactive subagent phase with interactive_subagent_ack → INFO, not FAIL."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        workflow=_workflow(
            [
                {
                    "phase": "ui_design",
                    "role": "ui-designer",
                    "execution_host": "subagent",
                    "interactive": True,
                    "interactive_subagent_ack": "deferred candidate",
                }
            ]
        ),
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_interactive_host"]
    assert len(findings) == 1
    assert findings[0].severity == "INFO"
    assert "deferred candidate" in findings[0].message


def test_b5_interactive_host_noninteractive_subagent_ok(tmp_path: Path) -> None:
    """Non-interactive phase on a subagent → no finding (the common case)."""
    _write_orchestrator(tmp_path, "Phase 4 dev_planning → tech-lead → dev-plan")
    _write_agent(tmp_path, "tech-lead", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        workflow=_workflow(
            [
                {
                    "phase": "dev_planning",
                    "role": "tech-lead",
                    "execution_host": "subagent",
                    "interactive": False,
                }
            ]
        ),
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    assert [f for f in report.findings if f.check_id == "B5_interactive_host"] == []


def test_b5_interactive_host_skipped_without_workflow(tmp_path: Path) -> None:
    """No workflow section → no B5_interactive_host findings (markdown-only project)."""
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    assert [f for f in report.findings if f.check_id == "B5_interactive_host"] == []


def test_b5_interactive_host_ok_when_platform_subagent_interactive(tmp_path: Path) -> None:
    """interactive subagent phase passes when the platform's subagents can interact."""
    _write_orchestrator(tmp_path, "Phase 3 ui_design → ui-designer → ui-spec")
    _write_agent(tmp_path, "ui-designer", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        platform="fancy-platform",
        workflow=_workflow(
            [
                {
                    "phase": "ui_design",
                    "role": "ui-designer",
                    "execution_host": "subagent",
                    "interactive": True,
                }
            ]
        ),
    )
    _write_platform_profile(tmp_path, "fancy-platform", subagent_interactive=True)

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    assert [f for f in report.findings if f.check_id == "B5_interactive_host"] == []


def test_b5_interactive_host_fails_when_platform_not_subagent_interactive(tmp_path: Path) -> None:
    """interactive subagent phase still FAILs when the platform's subagents can't interact."""
    _write_orchestrator(tmp_path, "Phase 3 ui_design → ui-designer → ui-spec")
    _write_agent(tmp_path, "ui-designer", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        platform="claude-code",
        workflow=_workflow(
            [
                {
                    "phase": "ui_design",
                    "role": "ui-designer",
                    "execution_host": "subagent",
                    "interactive": True,
                }
            ]
        ),
    )
    _write_platform_profile(tmp_path, "claude-code", subagent_interactive=False)

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_interactive_host"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"


def test_b5_phase_routing_prefers_workflow_over_markdown(tmp_path: Path) -> None:
    """When workflow exists, coverage routing is sourced from it, not the markdown.

    The markdown routes requirements → ghost-agent (undefined), but the
    structured workflow routes it → product-manager (defined). The structured
    source wins, so no coverage WARN about an undefined agent is raised.
    """
    _write_orchestrator(tmp_path, "Phase 1 requirements → ghost-agent → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_framework_json(
        tmp_path,
        workflow=_workflow(
            [
                {
                    "phase": "requirements",
                    "role": "product-manager",
                    "execution_host": "inline",
                    "interactive": True,
                }
            ]
        ),
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    ghost = [
        f
        for f in report.findings
        if f.check_id == "B5_workflow_coverage_matrix" and "ghost-agent" in f.message
    ]
    assert ghost == [], "structured workflow routing should override the markdown view"


# ---------------------------------------------------------------------------
# B5_hook_installed (validate_agent_result PostToolUse hook wired)
# ---------------------------------------------------------------------------


def _write_hooks_yaml(tmp_path: Path, body: str) -> None:
    hooks_dir = tmp_path / ".cataforge" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(body, encoding="utf-8")


def test_b5_hook_installed_skipped_when_hooks_yaml_absent(tmp_path: Path) -> None:
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    assert [f for f in report.findings if f.check_id == "B5_hook_installed"] == []


def test_b5_hook_installed_pass_when_wired(tmp_path: Path) -> None:
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_hooks_yaml(
        tmp_path,
        "schema_version: 2\n"
        "hooks:\n"
        "  PostToolUse:\n"
        "    - matcher_capability: agent_dispatch\n"
        "      script: validate_agent_result\n"
        "      type: observe\n",
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    assert [f for f in report.findings if f.check_id == "B5_hook_installed"] == []


def test_b5_hook_installed_fail_when_missing(tmp_path: Path) -> None:
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_hooks_yaml(
        tmp_path,
        "schema_version: 2\n"
        "hooks:\n"
        "  PostToolUse:\n"
        "    - matcher_capability: file_edit\n"
        "      script: lint_format\n"
        "      type: observe\n",
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_hook_installed"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
    assert "validate_agent_result" in findings[0].message


def test_b5_hook_installed_fail_on_wrong_capability(tmp_path: Path) -> None:
    _write_orchestrator(tmp_path, "Phase 1 requirements → product-manager → prd")
    _write_agent(tmp_path, "product-manager", skills=["doc-nav"])
    _write_skill(tmp_path, "doc-nav")
    _write_hooks_yaml(
        tmp_path,
        "schema_version: 2\n"
        "hooks:\n"
        "  PostToolUse:\n"
        "    - matcher_capability: file_edit\n"
        "      script: validate_agent_result\n"
        "      type: observe\n",
    )

    report = Report()
    check_b5_workflow_coverage(tmp_path, report)
    findings = [f for f in report.findings if f.check_id == "B5_hook_installed"]
    assert len(findings) == 1
    assert findings[0].severity == "FAIL"
