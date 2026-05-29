"""B5 — workflow coverage matrix + EVENT-LOG drift + hook installation."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from cataforge.core.event_log import EVENT_LOG_REL
from cataforge.core.paths import ProjectPaths

from .._constants import B5_CROSS_CUTTING, B5_SUBAGENTS
from .._discover import (
    discover_agents,
    discover_skills,
    parse_skills_field,
)
from .._framework_data import (
    read_dispatcher_skills,
    read_event_log_returns,
    read_event_log_threshold,
    read_framework_features,
)
from .._types import Report


def _parse_phase_routing(root: Path) -> dict[str, str]:
    """Return ``{phase_name: agent_id}`` parsed from orchestrator AGENT.md.

    Empty dict on missing file or unparseable content (callers treat as
    "no routing data — skip checks" rather than FAIL).
    """
    orch_path = ProjectPaths(root).agent_dir("orchestrator") / "AGENT.md"
    if not orch_path.is_file():
        return {}
    try:
        orch_text = orch_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    # "Phase N {name} → {agent} → {output}" patterns from the
    # Phase Routing block. The orchestrator AGENT.md format is stable
    # enough that a coarse regex suffices.
    phase_re = re.compile(
        r"Phase\s+\d+\s+(\w[\w_-]*)\s*[→\-]+\s*([\w-]+)",
        re.MULTILINE,
    )
    return {m.group(1): m.group(2) for m in phase_re.finditer(orch_text)}


def check_b5_workflow_coverage(root: Path, report: Report) -> None:
    """B5: workflow coverage triple-hop matrix + EVENT-LOG cross-check.

    Sub-checks (each emits findings under its own check_id):

    * ``B5_workflow_coverage_matrix`` — phase → agent single-hop:
      phases routing to undefined agents WARN; agents defined but never
      referenced WARN.  Phase targets that match a
      ``framework.json#/dispatcher_skills`` entry (e.g. ``tdd-engine``)
      are accepted as legitimate skill-as-router patterns.
    * ``B5_phase_skill_coverage`` — phase → agent → skill triple-hop:
      every phase-routed agent must declare ≥1 skill in its AGENT.md
      ``skills:`` field, and every declared skill must resolve to an
      existing ``.cataforge/skills/`` directory or builtin.
    * ``B5_eventlog_agent_return_drift`` — phase-routed agent has zero
      ``agent_return`` events in ``docs/EVENT-LOG.jsonl`` while the log
      has ≥ ``EVENT_LOG_DRIFT_MIN_EVENTS`` events overall (potential
      dead routing). Agents with returns but missing ``ref`` field on
      every return → WARN. Below threshold, emit a single INFO finding.
    * ``B5_feature_phase_alignment`` — every framework.json
      ``features[*].phase_guard`` value (when non-null) must reference a
      phase that has at least one routed agent.
    * ``B5_hook_installed`` — ``validate_agent_result`` PostToolUse hook
      must be wired in ``hooks.yaml`` under ``agent_dispatch``; without
      it, ``agent_return`` events never reach the EVENT-LOG and the
      drift check silently passes.
    """
    phase_to_agent = _parse_phase_routing(root)
    if not phase_to_agent:
        return

    agents = discover_agents(root)
    dispatcher_skills = read_dispatcher_skills(root)

    _check_coverage_matrix(phase_to_agent, agents, dispatcher_skills, report)
    _check_phase_skill_coverage(phase_to_agent, agents, root, report)
    _check_eventlog_drift(phase_to_agent, agents, dispatcher_skills, root, report)
    _check_feature_phase_alignment(phase_to_agent, root, report)
    _check_b5_hook_installed(root, report)


def _check_coverage_matrix(
    phase_to_agent: dict[str, str],
    agents: dict[str, Path],
    dispatcher_skills: set[str],
    report: Report,
) -> None:
    """Single-hop phase → agent: undefined targets WARN; unreferenced agents WARN."""
    for phase, agent in phase_to_agent.items():
        if agent in agents:
            continue
        if agent in dispatcher_skills:
            continue
        report.add(
            "B5_workflow_coverage_matrix",
            "WARN",
            "workflow",
            f"phase {phase!r} routes to {agent!r} which is neither a "
            f"defined agent under .cataforge/agents/ nor declared in "
            f"framework.json#/dispatcher_skills",
        )

    referenced_agents = set(phase_to_agent.values())
    referenced_agents.update(B5_SUBAGENTS)
    referenced_agents.update(B5_CROSS_CUTTING)

    for agent in sorted(agents):
        if agent not in referenced_agents:
            report.add(
                "B5_workflow_coverage_matrix",
                "WARN",
                f"agents/{agent}",
                "agent defined but not referenced by any phase routing or sub-agent dispatcher",
            )


def _check_phase_skill_coverage(
    phase_to_agent: dict[str, str],
    agents: dict[str, Path],
    root: Path,
    report: Report,
) -> None:
    """Triple-hop phase → agent → skill: each routed agent declares resolvable skills."""
    skills = discover_skills(root)
    builtin_skill_ids: set[str] = set()
    try:
        from cataforge.runtime.skill.loader import SkillLoader

        loader = SkillLoader(project_root=root)
        for meta in loader.discover():
            builtin_skill_ids.add(meta.id)
    except Exception:
        pass
    valid_skills = set(skills) | builtin_skill_ids

    for phase, agent in sorted(phase_to_agent.items()):
        if agent not in agents:
            continue
        try:
            agent_text = agents[agent].read_text(encoding="utf-8")
        except OSError:
            continue
        agent_skills = parse_skills_field(agent_text)
        if not agent_skills:
            report.add(
                "B5_phase_skill_coverage",
                "WARN",
                f"phase/{phase}",
                f"agent {agent!r} declares no skills: in AGENT.md "
                f"frontmatter; phase has no concrete capability",
            )
            continue
        for skill_id in agent_skills:
            if skill_id not in valid_skills:
                report.add(
                    "B5_phase_skill_coverage",
                    "WARN",
                    f"agents/{agent}",
                    f"skill {skill_id!r} listed under {agent!r} skills: "
                    f"but not found in .cataforge/skills/ or builtins",
                )


def _check_eventlog_drift(
    phase_to_agent: dict[str, str],
    agents: dict[str, Path],
    dispatcher_skills: set[str],
    root: Path,
    report: Report,
) -> None:
    """Cross-check phase-routed agents against agent_return events in EVENT-LOG."""
    log_path = root / EVENT_LOG_REL
    log_exists = log_path.is_file()
    returns, returns_with_ref = read_event_log_returns(root)
    total_returns = sum(returns.values())
    threshold = read_event_log_threshold(root)
    if not log_exists:
        # No EVENT-LOG yet → the project hasn't deployed event-emitting
        # workflows. Silent skip — emitting INFO here would be noise.
        pass
    elif total_returns < threshold:
        # Log exists but data is too sparse to tell signal from absence.
        # Emit a single INFO so users know the check is wired.
        report.add(
            "B5_eventlog_agent_return_drift",
            "INFO",
            "workflow",
            f"EVENT-LOG.jsonl has {total_returns} agent_return event(s); "
            f"drift check skipped until ≥ {threshold} events accumulate "
            "(override via constants.EVENT_LOG_DRIFT_MIN_EVENTS)",
        )
    else:
        for phase, agent in sorted(phase_to_agent.items()):
            if agent in dispatcher_skills:
                continue
            if agent not in agents:
                continue
            if returns.get(agent, 0) == 0:
                # Total events past the threshold AND a phase-routed agent
                # contributed nothing is a strong dead-routing signal. The
                # threshold gate above filters sparse-data noise, so this
                # is not a "haven't seen it yet" case — it's a mis-wire.
                report.add(
                    "B5_eventlog_agent_return_drift",
                    "FAIL",
                    f"phase/{phase}",
                    f"phase routes to {agent!r} but EVENT-LOG.jsonl has "
                    f"0 agent_return events for it across "
                    f"{total_returns} total returns "
                    f"(threshold {threshold}); strong dead-routing "
                    f"signal — verify validate_agent_result hook is "
                    f"installed and dispatch path actually reaches "
                    f"this agent",
                )
        # Returns exist but none carry a ref (output_path) field.
        for agent, count in sorted(returns.items()):
            if returns_with_ref.get(agent, 0) == 0 and count > 0:
                report.add(
                    "B5_eventlog_agent_return_drift",
                    "WARN",
                    f"agents/{agent}",
                    f"all {count} agent_return events for {agent!r} lack "
                    f"a 'ref' field (output_path); EVENT-LOG schema "
                    f"allows it but downstream sprint-review / retrospective "
                    f"can't trace deliverables",
                )


def _check_feature_phase_alignment(
    phase_to_agent: dict[str, str], root: Path, report: Report
) -> None:
    """Every framework.json features[*].phase_guard must name a routed phase."""
    features = read_framework_features(root)
    valid_phases = set(phase_to_agent.keys())
    for feat_id, feat_meta in sorted(features.items()):
        guard = feat_meta.get("phase_guard")
        if guard is None or not isinstance(guard, str):
            continue
        if guard not in valid_phases:
            report.add(
                "B5_feature_phase_alignment",
                "WARN",
                f"framework.json/features/{feat_id}",
                f"phase_guard={guard!r} does not appear in "
                f"orchestrator AGENT.md Phase Routing "
                f"(known phases: {sorted(valid_phases)})",
            )


def _check_b5_hook_installed(root: Path, report: Report) -> None:
    """Verify validate_agent_result is wired as a PostToolUse hook.

    Without it, ``agent_return`` events never reach EVENT-LOG.jsonl,
    making B5_eventlog_agent_return_drift silently degenerate (it sees
    0 returns for every agent and either no-ops on sparse data or
    FAILs spuriously on real activity that just isn't being captured).
    This check fails FAST so the user fixes the hook before chasing
    phantom drift signals.
    """
    hooks_yaml = ProjectPaths(root).hooks_spec
    if not hooks_yaml.is_file():
        return  # B6 will FAIL on this independently
    try:
        hooks_data = yaml.safe_load(hooks_yaml.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return
    if not isinstance(hooks_data, dict):
        return

    post_entries = (hooks_data.get("hooks") or {}).get("PostToolUse") or []
    if not isinstance(post_entries, list):
        return

    found = False
    for entry in post_entries:
        if not isinstance(entry, dict):
            continue
        script = entry.get("script")
        cap = entry.get("matcher_capability")
        if script == "validate_agent_result" and cap == "agent_dispatch":
            found = True
            break

    if not found:
        report.add(
            "B5_hook_installed",
            "FAIL",
            "hooks/hooks.yaml",
            "validate_agent_result is not wired as a PostToolUse hook "
            "with matcher_capability=agent_dispatch; agent_return "
            "events will never be logged, leaving B5 drift detection "
            "blind",
        )
