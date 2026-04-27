"""framework_check.py — Framework meta-asset structural audit (Layer 1).

Independent sub-checks driven by ``--scope`` and ``--focus``:

* B1-α: required SKILL.md / AGENT.md sections
* B1-β: file size threshold (META_DOC_SPLIT_THRESHOLD_LINES)
* B2-α: cross-reference graph (AGENT.md.skills + SKILL.md.depends +
  framework.json.features → resolves to existing assets)
* B3-α: SKILL.md "## Layer 1 检查项" ↔ builtin CHECKS_MANIFEST drift
* B4-α: hard-coded constant drift (numeric literals that should
  reference COMMON-RULES constants)
* B5-α: workflow coverage matrix (ORCHESTRATOR-PROTOCOLS dispatch
  table × framework.json.features × agents)
* B6-α: hook script reachability — every script referenced in
  hooks.yaml resolves to a real .py file (builtin
  ``cataforge.hook.scripts.<name>`` or
  ``.cataforge/hooks/custom/<name>.py``)
* B6-β: hook script syntax — each resolved script is ast-parseable
* B6-γ: matcher_capability values are members of
  ``CAPABILITY_IDS`` ∪ ``EXTENDED_CAPABILITY_IDS``
* B6-δ: per-platform ``hooks.degradation`` parity — every hook script
  in hooks.yaml has a degradation flag in each ``profile.yaml``, and
  no orphan flags (degradation entries for scripts no longer in
  hooks.yaml)

Usage:
  python -m cataforge.skill.builtins.framework_review.framework_check \\
        <scope: agents|skills|hooks|rules|workflow|all> \\
        [--focus B1,B2,B3,B4,B5,B6] \\
        [--root <project_root>] \\
        [--meta-size-threshold N]

Exit codes follow §Layer 1 调用协议: 0=PASS, 1=FAIL (any check found
problems), 2=usage error.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.resources
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from cataforge.utils.common import ensure_utf8_stdio
from cataforge.utils.frontmatter import split_yaml_frontmatter

DEFAULT_META_SIZE = 500

REQUIRED_SECTIONS_SKILL = {
    # Capability boundary is the only hard requirement — every skill
    # must declare 能做/不做.  Input/Output/Op-steps accept multiple
    # synonyms because legacy skills use varied section titles
    # (调度输入 / 执行步骤 / 平台调度实现) that mean the same thing.
    "能力边界": r"^##\s+能力边界",
    "输入定义": r"^##\s+(输入规范|调度输入|输入|Input(\s+Contract)?)",
    "输出定义": r"^##\s+(输出规范|输出|Output(\s+Contract)?|返回值|执行结果)",
    "操作步骤": (
        r"^##\s+(操作指令|执行流程|执行步骤|执行|步骤|"
        r"角色假设|平台调度实现|Anti-?Patterns)"
    ),
}

REQUIRED_SECTIONS_AGENT = {
    "Identity": r"^##\s+(Identity|身份|角色)",
    "Input Contract": r"^##\s+(Input Contract|输入契约|输入规范)",
    "Output Contract": r"^##\s+(Output Contract|输出契约|输出规范)",
    "Anti-Patterns": r"^##\s+Anti-?Patterns",
}

# Skills exempted from B1-α required-section enforcement because their
# AGENT.md / SKILL.md serves a different role (orchestrator's protocol
# index, agent-dispatch's runtime adapter, etc.) and forcing them into
# a uniform shape would dilute clarity.
B1_REQUIRED_SECTIONS_EXEMPT_SKILLS = frozenset({
    "agent-dispatch",  # runtime translation layer — different shape
    "doc-gen",         # template registry — different shape
    "doc-nav",         # loader hint — different shape
    "research",        # interactive playbook — different shape
    "start-orchestrator",  # entry trampoline — different shape
    "tdd-engine",      # macro skill spanning multiple sub-agents
    "workflow-framework-generator",  # scaffold generator — different shape
})

B1_REQUIRED_SECTIONS_EXEMPT_AGENTS = frozenset({
    "orchestrator",  # has Phase Routing/Startup Protocol instead of
                     # Input/Output Contract; protocols live in
                     # ORCHESTRATOR-PROTOCOLS.md
})

# Skills exempt from "orphan skill" warning. These are infrastructure
# skills called by orchestrator/main-thread or by other skills directly,
# not advertised in any AGENT.md skills: list.
ORPHAN_SKILL_WHITELIST = frozenset({
    "agent-dispatch",
    "tdd-engine",
    "change-guard",
    "start-orchestrator",
    "doc-nav",
    "doc-gen",
    "research",
    "debug",
    "self-update",
    "workflow-framework-generator",
    "platform-audit",
    "framework-review",
})

# Constants whose names must be referenced instead of bare numerics.
# (constant_name, numeric_pattern, doc_hint)
CONSTANT_LITERALS: tuple[tuple[str, str, str], ...] = (
    ("MAX_QUESTIONS_PER_BATCH", r"≤\s*3\s*(问|题|个问题)", "≤3 问"),
    ("DOC_SPLIT_THRESHOLD_LINES", r"(>|超过|≥)\s*300\s*行", ">300 行"),
    ("DOC_REVIEW_L2_SKIP_THRESHOLD_LINES", r"<\s*200\s*行", "<200 行"),
    ("TDD_LIGHT_LOC_THRESHOLD", r"(≤|<)\s*50\s*(LOC|loc|行代码)", "≤50 LOC"),
    ("RETRO_TRIGGER_SELF_CAUSED", r"(累计|≥)\s*5\s*条", "≥5 条"),
    ("SPRINT_REVIEW_MICRO_TASK_COUNT", r"(≤|<=)\s*2\s*个任务", "≤2 个任务"),
)


@dataclass
class Finding:
    check_id: str
    severity: str  # FAIL / WARN
    location: str
    message: str

    def render(self) -> str:
        return f"[{self.severity}] {self.check_id} @ {self.location}: {self.message}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "FAIL")

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "WARN")

    def add(
        self, check_id: str, severity: str, location: str, message: str
    ) -> None:
        self.findings.append(Finding(check_id, severity, location, message))


def discover_agents(root: Path) -> dict[str, Path]:
    base = root / ".cataforge" / "agents"
    if not base.is_dir():
        return {}
    return {
        d.name: d / "AGENT.md"
        for d in base.iterdir()
        if d.is_dir() and (d / "AGENT.md").is_file()
    }


def discover_skills(root: Path) -> dict[str, Path]:
    base = root / ".cataforge" / "skills"
    if not base.is_dir():
        return {}
    return {
        d.name: d / "SKILL.md"
        for d in base.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    }


def parse_skills_field(content: str) -> list[str]:
    """Extract the ``skills:`` list from a YAML frontmatter block."""
    fm, _ = split_yaml_frontmatter(content)
    if not fm:
        return []
    raw = fm.get("skills") or []
    if isinstance(raw, str):
        raw = [s.strip() for s in raw.split(",") if s.strip()]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        # Tolerate "penpot-review  # 仅当 ..." inline comments.
        if isinstance(item, str):
            item = item.split("#", 1)[0].strip()
            if item:
                out.append(item)
    return out


def parse_depends_field(content: str) -> list[str]:
    fm, _ = split_yaml_frontmatter(content)
    if not fm:
        return []
    raw = fm.get("depends") or []
    if isinstance(raw, str):
        raw = [s.strip() for s in raw.split(",") if s.strip()]
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def check_b1_required_sections(
    root: Path, scope: str, report: Report
) -> None:
    """B1-α: required structural sections in AGENT.md / SKILL.md."""
    targets: list[tuple[str, Path, dict[str, str]]] = []
    if scope in ("agents", "all"):
        for aid, path in discover_agents(root).items():
            if aid in B1_REQUIRED_SECTIONS_EXEMPT_AGENTS:
                continue
            targets.append((f"agents/{aid}", path, REQUIRED_SECTIONS_AGENT))
    if scope in ("skills", "all"):
        for sid, path in discover_skills(root).items():
            if sid in B1_REQUIRED_SECTIONS_EXEMPT_SKILLS:
                continue
            targets.append((f"skills/{sid}", path, REQUIRED_SECTIONS_SKILL))

    for label, path, required in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            report.add("B1_required_sections", "FAIL", label, f"cannot read: {exc}")
            continue
        for sect_name, pattern in required.items():
            if not re.search(pattern, text, re.MULTILINE):
                report.add(
                    "B1_required_sections",
                    "FAIL",
                    label,
                    f"missing section: {sect_name}",
                )


def check_b1_size(
    root: Path, scope: str, threshold: int, report: Report
) -> None:
    """B1-β: META_DOC_SPLIT_THRESHOLD_LINES soft cap."""
    targets: list[tuple[str, Path]] = []
    if scope in ("agents", "all"):
        for aid, path in discover_agents(root).items():
            targets.append((f"agents/{aid}", path))
    if scope in ("skills", "all"):
        for sid, path in discover_skills(root).items():
            targets.append((f"skills/{sid}", path))
    if scope in ("rules", "all"):
        rules_dir = root / ".cataforge" / "rules"
        if rules_dir.is_dir():
            for path in sorted(rules_dir.rglob("*.md")):
                try:
                    rel = path.relative_to(root).as_posix()
                except ValueError:
                    rel = str(path)
                targets.append((rel, path))

    for label, path in targets:
        try:
            line_count = sum(1 for _ in path.open(encoding="utf-8"))
        except OSError:
            continue
        if line_count > threshold:
            report.add(
                "B1_size_threshold",
                "WARN",
                label,
                f"{line_count} lines > META_DOC_SPLIT_THRESHOLD_LINES "
                f"({threshold}); 建议拆分为分卷",
            )


def check_b2_cross_references(root: Path, report: Report) -> None:
    """B2-α: skills referenced in AGENT.md / SKILL.md must resolve."""
    agents = discover_agents(root)
    skills = discover_skills(root)

    # Builtin skill ids — discovered via the package, not file system —
    # because override-via-SKILL.md may not be present in user projects.
    try:
        from cataforge.skill.loader import SkillLoader

        loader = SkillLoader(project_root=root)
        for meta in loader.discover():
            if meta.id not in skills:
                # Builtin without override — still valid reference target.
                skills[meta.id] = Path("(builtin)")
    except Exception:
        pass

    referenced: dict[str, set[str]] = {}

    for aid, path in agents.items():
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for skill_id in parse_skills_field(content):
            referenced.setdefault(skill_id, set()).add(f"agents/{aid}")

    for sid, path in skills.items():
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for dep_id in parse_depends_field(content):
            referenced.setdefault(dep_id, set()).add(f"skills/{sid}")

    # Missing references → FAIL
    for skill_id, refs in sorted(referenced.items()):
        if skill_id not in skills:
            for ref in sorted(refs):
                report.add(
                    "B2_cross_reference_graph",
                    "FAIL",
                    ref,
                    f"references missing skill/agent: {skill_id!r}",
                )

    # Orphan skills (defined but never referenced) → WARN, with whitelist
    for skill_id in sorted(skills):
        if skill_id in ORPHAN_SKILL_WHITELIST:
            continue
        if skill_id not in referenced:
            report.add(
                "B2_cross_reference_graph",
                "WARN",
                f"skills/{skill_id}",
                "orphan skill: not referenced by any AGENT.md.skills "
                "or SKILL.md.depends",
            )


_CHECK_ID_ANCHOR_RE = re.compile(r"<!--\s*check_id:\s*([\w.-]+)\s*-->")
_DELEGATION_RE = re.compile(r"权威清单见.*?CHECKS_MANIFEST", re.DOTALL)


def check_b3_manifest_drift(root: Path, report: Report) -> None:
    """B3-α: SKILL.md '## Layer 1 检查项' ↔ CHECKS_MANIFEST.

    Three reconciliation strategies, in order of preference:

    1. **Anchor mode** — if the section contains one or more
       ``<!-- check_id: xxx -->`` HTML comments, do a precise bidirectional
       ID check: every anchor must point at a real manifest entry, and
       every non-delegated manifest entry must have an anchor. False
       negatives from token rewording disappear; false positives from
       loose phrasing also disappear. Preferred for new skills with
       per-entry prose.

    2. **Delegation mode** — if the section contains the canonical phrase
       ``权威清单见 ...CHECKS_MANIFEST``, the SKILL.md is explicitly
       deferring per-entry documentation to the manifest. We still verify
       the manifest exists, but skip entry-by-entry comparison.

    3. **Token heuristic (legacy fallback)** — if neither anchors nor
       delegation are present, fall back to the original "every manifest
       entry's title has at least one significant token in the prose"
       check. Soft, but catches obvious staleness in skills that pre-date
       the anchor and delegation conventions.
    """
    # Map skill id → builtin module name. Only review-class skills
    # (whose builtin runs Layer 1 checks) are tracked here.
    # task-dep-analysis is a deterministic graph algorithm — its
    # CHECKS_MANIFEST describes algorithms, not Layer 1 checks, so
    # prose drift detection doesn't apply.
    builtin_map = {
        "code-review": "cataforge.skill.builtins.code_review",
        "doc-review": "cataforge.skill.builtins.doc_review",
        "sprint-review": "cataforge.skill.builtins.sprint_review",
        "framework-review": "cataforge.skill.builtins.framework_review",
    }

    for skill_id, module_name in builtin_map.items():
        skill_md = root / ".cataforge" / "skills" / skill_id / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError as exc:
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                f"cannot read SKILL.md: {exc}",
            )
            continue

        section_match = re.search(
            r"^##\s+Layer 1 检查项[^\n]*\n(.*?)(?=^##\s|\Z)",
            text,
            re.DOTALL | re.MULTILINE,
        )
        if not section_match:
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                "缺少 '## Layer 1 检查项' 段；builtin manifest 已存在",
            )
            continue

        section_text = section_match.group(1)

        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                f"cannot import {module_name}: {exc}",
            )
            continue

        manifest = getattr(module, "CHECKS_MANIFEST", None)
        if not manifest:
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                f"{module_name}.CHECKS_MANIFEST 不存在或为空",
            )
            continue

        anchored_ids = set(_CHECK_ID_ANCHOR_RE.findall(section_text))
        delegated = bool(_DELEGATION_RE.search(section_text))

        if anchored_ids:
            # Strategy 1: anchor mode. Bidirectional ID check.
            _check_b3_anchors(skill_id, anchored_ids, manifest, delegated, report)
            continue
        if delegated:
            # Strategy 2: delegation mode. Manifest existence is the
            # only contract.
            continue
        # Strategy 3: token heuristic fallback.
        _check_b3_tokens(skill_id, section_text, manifest, report)


def _check_b3_anchors(
    skill_id: str,
    anchored_ids: set[str],
    manifest: tuple[dict[str, str], ...],
    delegated: bool,
    report: Report,
) -> None:
    """Bidirectional check_id anchor reconciliation.

    Two failure modes:

    * **Orphan anchor** — ``<!-- check_id: xxx -->`` references an ID that
      no manifest entry declares. Indicates a SKILL.md edit that wasn't
      mirrored in the builtin (e.g. a check was renamed in the manifest
      but the prose anchor stayed on the old ID).
    * **Missing anchor** — a manifest entry has no anchor in the prose.
      Skipped when the section also has the delegation marker (allowing
      mixed delegation + selectively-anchored entries: the manifest is
      authoritative but the most-important entries can still surface in
      prose without forcing all of them to).
    """
    manifest_ids = {str(entry.get("id", "")).strip() for entry in manifest}
    manifest_ids.discard("")

    for anchor_id in sorted(anchored_ids - manifest_ids):
        report.add(
            "B3_manifest_drift",
            "FAIL",
            f"skills/{skill_id}",
            f"check_id anchor {anchor_id!r} has no matching manifest "
            "entry — was the check renamed in the builtin without "
            "updating the SKILL.md anchor?",
        )

    if delegated:
        # When mixed with delegation, anchored entries are documentation
        # bonuses; non-anchored manifest entries don't need surfacing.
        return

    for missing_id in sorted(manifest_ids - anchored_ids):
        report.add(
            "B3_manifest_drift",
            "FAIL",
            f"skills/{skill_id}",
            f"manifest entry {missing_id!r} has no <!-- check_id: ... --> "
            "anchor in the SKILL.md prose — anchor mode requires every "
            "manifest entry to be surfaced (or add the delegation marker "
            "to opt out for less-important entries)",
        )


def _check_b3_tokens(
    skill_id: str,
    section_text: str,
    manifest: tuple[dict[str, str], ...],
    report: Report,
) -> None:
    """Legacy token-overlap heuristic.

    Soft drift detection: every manifest entry's title must have at
    least one significant token appearing in the prose section. We're
    not parsing markdown — humans may rephrase, but the critical
    keyword should survive. A missing title hits FAIL.
    """
    for entry in manifest:
        title = str(entry.get("title", "")).strip()
        if not title:
            continue
        tokens = [
            t for t in re.split(r"[\s/(),:：]+", title)
            if t and len(t) >= 3 and not t.isascii() or t.lower() in {"check", "ac", "id"}
        ]
        sig_tokens = [t for t in tokens if len(t) >= 3]
        if not sig_tokens:
            continue
        if not any(t in section_text for t in sig_tokens[:3]):
            report.add(
                "B3_manifest_drift",
                "FAIL",
                f"skills/{skill_id}",
                f"manifest entry not surfaced in SKILL.md: {title!r}",
            )


def check_b4_hardcoded_constants(root: Path, report: Report) -> None:
    """B4-α: bare numeric literals that should reference constants."""
    scan_roots = (
        root / ".cataforge" / "agents",
        root / ".cataforge" / "skills",
        root / ".cataforge" / "rules",
    )
    for base in scan_roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = str(path)
            in_code_block = False
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.lstrip()
                if stripped.startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block:
                    continue
                # Strip backtick-wrapped spans first: those are quoted
                # examples (e.g. "`≤3 问`" appearing in framework-review's
                # own SKILL.md to *describe* the rule), not literal usage.
                line_outside_inline_code = re.sub(r"`[^`]*`", "", line)
                # Defensively also drop the line entirely if it's the
                # constants-table row that *defines* the value (e.g.
                # COMMON-RULES.md's `| MAX_QUESTIONS_PER_BATCH | 3 |` row
                # talks about it in plain prose at the table's caption).
                # The "Why" / "How to apply" rows are markdown table
                # rows starting with `|`, so drop those too.
                if stripped.startswith("|"):
                    continue
                for const_name, pattern, hint in CONSTANT_LITERALS:
                    if const_name in line:
                        continue
                    if re.search(pattern, line_outside_inline_code):
                        report.add(
                            "B4_hardcoded_constants",
                            "WARN",
                            f"{rel}:{lineno}",
                            f"裸数值 {hint!r} 未引用常量名 {const_name}",
                        )


def _parse_phase_routing(root: Path) -> dict[str, str]:
    """Return ``{phase_name: agent_id}`` parsed from orchestrator AGENT.md.

    Empty dict on missing file or unparseable content (callers treat as
    "no routing data — skip checks" rather than FAIL).
    """
    orch_path = root / ".cataforge" / "agents" / "orchestrator" / "AGENT.md"
    if not orch_path.is_file():
        return {}
    try:
        orch_text = orch_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    # Extract "Phase N {name} → {agent} → {output}" patterns from the
    # Phase Routing block. The orchestrator AGENT.md format is stable
    # enough that a coarse regex suffices.
    phase_re = re.compile(
        r"Phase\s+\d+\s+(\w[\w_-]*)\s*[→\-]+\s*([\w-]+)",
        re.MULTILINE,
    )
    return {m.group(1): m.group(2) for m in phase_re.finditer(orch_text)}


def _read_event_log_returns(root: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Return ``({agent: return_count}, {agent: returns_with_ref})``.

    Reads ``docs/EVENT-LOG.jsonl`` line-by-line. Tolerates malformed lines
    (skipped silently) since the log is append-only and may have partial
    writes from crashed processes. Returns empty dicts if the file is
    missing — caller treats that as "no event data, skip cross-check"
    rather than treating absence as evidence of dead routing.
    """
    log_path = root / "docs" / "EVENT-LOG.jsonl"
    if not log_path.is_file():
        return {}, {}

    returns: dict[str, int] = {}
    returns_with_ref: dict[str, int] = {}
    try:
        with log_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get("event") != "agent_return":
                    continue
                agent = record.get("agent")
                if not isinstance(agent, str) or not agent:
                    continue
                returns[agent] = returns.get(agent, 0) + 1
                ref = record.get("ref")
                if isinstance(ref, str) and ref:
                    returns_with_ref[agent] = returns_with_ref.get(agent, 0) + 1
    except OSError:
        pass
    return returns, returns_with_ref


def _read_framework_features(root: Path) -> dict[str, dict[str, object]]:
    """Return ``framework.json#/features`` mapping, or empty on failure."""
    fw_json = root / ".cataforge" / "framework.json"
    if not fw_json.is_file():
        return {}
    try:
        data = json.loads(fw_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    features = data.get("features")
    if not isinstance(features, dict):
        return {}
    return {
        str(k): v for k, v in features.items() if isinstance(v, dict)
    }


# Sub-agents not directly phase-routed but invoked by orchestrator or
# tdd-engine — counted as "referenced" so B5 doesn't warn on them.
_B5_SUBAGENTS = frozenset({"test-writer", "implementer", "refactorer"})
_B5_CROSS_CUTTING = frozenset({
    "reviewer", "debugger", "orchestrator", "reflector",
})


def check_b5_workflow_coverage(root: Path, report: Report) -> None:
    """B5: workflow coverage triple-hop matrix + EVENT-LOG cross-check.

    Sub-checks (each emits findings under its own check_id so the
    CHECKS_MANIFEST stays granular like B6):

    * ``B5_workflow_coverage_matrix`` — phase → agent single-hop
      (existing): phases routing to undefined agents WARN; agents
      defined but never referenced WARN.
    * ``B5_phase_skill_coverage`` — phase → agent → skill triple-hop:
      every phase-routed agent must declare ≥1 skill in its AGENT.md
      ``skills:`` field, and every declared skill must resolve to an
      existing ``.cataforge/skills/`` directory or builtin.
    * ``B5_eventlog_agent_return_drift`` — phase-routed agent has zero
      ``agent_return`` events in ``docs/EVENT-LOG.jsonl`` while the log
      itself has ≥10 events overall (potential dead routing). Agents
      with returns but missing ``ref`` field on every return → WARN
      (output_path schema gap).
    * ``B5_feature_phase_alignment`` — every framework.json
      ``features[*].phase_guard`` value (when non-null) must reference a
      phase that has at least one routed agent.
    """
    phase_to_agent = _parse_phase_routing(root)
    if not phase_to_agent:
        return

    agents = discover_agents(root)

    # ---- B5_workflow_coverage_matrix (existing single-hop) ----
    for phase, agent in phase_to_agent.items():
        if agent not in agents and not agent.endswith("-engine"):
            # tdd-engine is a skill, not an agent — accepted.
            report.add(
                "B5_workflow_coverage_matrix",
                "WARN",
                "workflow",
                f"phase {phase!r} routes to {agent!r} which is not a "
                f"defined agent under .cataforge/agents/",
            )

    referenced_agents = set(phase_to_agent.values())
    referenced_agents.update(_B5_SUBAGENTS)
    referenced_agents.update(_B5_CROSS_CUTTING)

    for agent in sorted(agents):
        if agent not in referenced_agents:
            report.add(
                "B5_workflow_coverage_matrix",
                "WARN",
                f"agents/{agent}",
                "agent defined but not referenced by any phase routing "
                "or sub-agent dispatcher",
            )

    # ---- B5_phase_skill_coverage (triple-hop: phase → agent → skill) ----
    skills = discover_skills(root)
    builtin_skill_ids: set[str] = set()
    try:
        from cataforge.skill.loader import SkillLoader

        loader = SkillLoader(project_root=root)
        for meta in loader.discover():
            builtin_skill_ids.add(meta.id)
    except Exception:
        pass
    valid_skills = set(skills) | builtin_skill_ids

    for phase, agent in sorted(phase_to_agent.items()):
        if agent not in agents:
            continue  # already flagged by single-hop check
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

    # ---- B5_eventlog_agent_return_drift (EVENT-LOG cross-check) ----
    returns, returns_with_ref = _read_event_log_returns(root)
    total_returns = sum(returns.values())
    # Heuristic threshold: only flag drift when the log has accumulated
    # enough events to be representative. A fresh project with 0-9 events
    # legitimately has phase-routed agents that haven't run yet.
    if total_returns >= 10:
        for phase, agent in sorted(phase_to_agent.items()):
            if agent.endswith("-engine"):
                continue  # tdd-engine emits returns under sub-agent ids
            if agent not in agents:
                continue
            if returns.get(agent, 0) == 0:
                report.add(
                    "B5_eventlog_agent_return_drift",
                    "WARN",
                    f"phase/{phase}",
                    f"phase routes to {agent!r} but EVENT-LOG.jsonl has "
                    f"0 agent_return events for it across "
                    f"{total_returns} total returns (potential dead routing)",
                )
        # Per-agent: returns exist but none carry a ref (output_path) field.
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

    # ---- B5_feature_phase_alignment (framework.json features) ----
    features = _read_framework_features(root)
    valid_phases = set(phase_to_agent.keys())
    for feat_id, feat_meta in sorted(features.items()):
        guard = feat_meta.get("phase_guard")
        if guard is None or not isinstance(guard, str):
            continue  # null guard = applies to all phases, skip
        if guard not in valid_phases:
            report.add(
                "B5_feature_phase_alignment",
                "WARN",
                f"framework.json/features/{feat_id}",
                f"phase_guard={guard!r} does not appear in "
                f"orchestrator AGENT.md Phase Routing "
                f"(known phases: {sorted(valid_phases)})",
            )


def _load_hooks_manifest_names() -> set[str]:
    """Return ``{name}`` for HOOKS_MANIFEST entries, or empty on import failure.

    Lazy import keeps framework-review usable on older wheels that ship
    cataforge without the manifest module — B6-ε just becomes a no-op
    rather than an exception.
    """
    try:
        from cataforge.hook.manifest import manifest_names
    except ImportError:
        return set()
    return set(manifest_names())


def check_b6_hook_consistency(root: Path, report: Report) -> None:
    """B6: hook 元资产审查.

    Five sub-checks operating on ``.cataforge/hooks/hooks.yaml`` and the
    per-platform ``profile.yaml`` files:

    * α — script reachability: every ``script`` referenced in hooks.yaml
      resolves to a real .py file.  Builtins live in
      ``cataforge.hook.scripts.<name>`` (resolved via ``importlib.resources``
      so editable / wheel installs both work); customs are referenced as
      ``custom:<name>`` and live at ``.cataforge/hooks/custom/<name>.py``.
    * β — script syntax: each resolved script is ``ast.parse``-able.
      Catches half-edited scripts before deploy generates broken hook
      configs.
    * γ — matcher_capability validity: each ``matcher_capability`` value
      is a member of ``CAPABILITY_IDS`` ∪ ``EXTENDED_CAPABILITY_IDS``.
      A typo here silently produces a hook that never fires (the bridge
      can't map an unknown capability to a platform tool).
    * δ — degradation parity: for every platform ``profile.yaml`` under
      ``.cataforge/platforms/``, the keys of ``hooks.degradation`` must
      exactly match the set of script names referenced in hooks.yaml.
      Missing flag → WARN (script will deploy with implicit ``native``);
      orphan flag → WARN (degradation entry for a script that no longer
      exists in hooks.yaml — silent dead config).
    * ε — manifest drift: every non-``custom:`` script in hooks.yaml
      must appear in ``cataforge.hook.manifest.HOOKS_MANIFEST``. Catches
      "wired a helper module as a hook" bugs that B6-α (file existence)
      lets slip — e.g. ``script: notify_util`` would pass α (file exists)
      but is not actually a hook target.
    """
    hooks_yaml = root / ".cataforge" / "hooks" / "hooks.yaml"
    if not hooks_yaml.is_file():
        return
    try:
        hooks_data = yaml.safe_load(hooks_yaml.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        report.add(
            "B6_hook_consistency",
            "FAIL",
            "hooks/hooks.yaml",
            f"failed to parse hooks.yaml: {e}",
        )
        return
    if not isinstance(hooks_data, dict):
        return

    referenced_scripts: set[str] = set()
    referenced_caps: set[str] = set()
    for _event, entries in (hooks_data.get("hooks") or {}).items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            script = entry.get("script")
            cap = entry.get("matcher_capability")
            if script:
                referenced_scripts.add(script)
            if cap:
                referenced_caps.add(cap)

    # α + β: script reachability and syntax.
    builtin_dir = _resolve_builtin_hook_dir()
    custom_dir = root / ".cataforge" / "hooks" / "custom"
    for script in sorted(referenced_scripts):
        py_path = _resolve_hook_script(script, builtin_dir, custom_dir)
        if py_path is None:
            report.add(
                "B6_hook_script_reachability",
                "FAIL",
                f"hooks/{script}",
                "script referenced in hooks.yaml but no .py file found "
                "(checked builtin cataforge.hook.scripts and "
                ".cataforge/hooks/custom/)",
            )
            continue
        try:
            ast.parse(py_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as e:
            report.add(
                "B6_hook_script_syntax",
                "FAIL",
                f"hooks/{script}",
                f"script {py_path.name} not ast-parseable: {e}",
            )

    # γ: matcher_capability validity.
    valid_caps = _load_capability_ids()
    if valid_caps:
        for cap in sorted(referenced_caps):
            if cap not in valid_caps:
                report.add(
                    "B6_hook_matcher_capability",
                    "FAIL",
                    f"hooks/{cap}",
                    f"matcher_capability {cap!r} not in CAPABILITY_IDS / "
                    "EXTENDED_CAPABILITY_IDS — hook will silently never "
                    "fire (bridge can't map unknown capability to a "
                    "platform tool)",
                )

    # ε: hooks.yaml builtin scripts must appear in HOOKS_MANIFEST.
    manifest_names_set = _load_hooks_manifest_names()
    if manifest_names_set:
        for script in sorted(referenced_scripts):
            if script.startswith("custom:"):
                continue  # custom scripts not subject to manifest
            if script not in manifest_names_set:
                report.add(
                    "B6_hook_manifest_drift",
                    "FAIL",
                    f"hooks/{script}",
                    f"hooks.yaml references {script!r} but it is not in "
                    f"cataforge.hook.manifest.HOOKS_MANIFEST; either "
                    f"register it there (preferred — declares it as a "
                    f"hook target) or use 'custom:' prefix to opt out",
                )
        # Reverse: every manifest entry that's never wired in hooks.yaml
        # is dead inventory (WARN — the script ships in the wheel but
        # nothing exercises it).
        wired_builtins = {
            s for s in referenced_scripts if not s.startswith("custom:")
        }
        for unwired in sorted(manifest_names_set - wired_builtins):
            report.add(
                "B6_hook_manifest_drift",
                "WARN",
                f"hooks/{unwired}",
                f"HOOKS_MANIFEST entry {unwired!r} not referenced by "
                f"hooks.yaml; either wire it in or remove the manifest "
                f"entry to avoid shipping dead inventory",
            )

    # δ: per-platform degradation parity.
    platforms_dir = root / ".cataforge" / "platforms"
    if not platforms_dir.is_dir():
        return
    for plat_dir in sorted(platforms_dir.iterdir()):
        if not plat_dir.is_dir():
            continue
        profile_path = plat_dir / "profile.yaml"
        if not profile_path.is_file():
            continue
        try:
            profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(profile, dict):
            continue
        degradation = ((profile.get("hooks") or {}).get("degradation")) or {}
        if not isinstance(degradation, dict):
            continue
        declared = set(degradation.keys())
        # custom: scripts ship per-project; degradation key drops the prefix.
        normalized_refs = {
            s.removeprefix("custom:") for s in referenced_scripts
        }
        missing = sorted(normalized_refs - declared)
        orphan = sorted(declared - normalized_refs)
        for script in missing:
            report.add(
                "B6_hook_degradation_coverage",
                "WARN",
                f"platforms/{plat_dir.name}",
                f"script {script!r} referenced in hooks.yaml but has no "
                "degradation flag in this profile.yaml — deploy will "
                "default to implicit 'native' which may silently mask a "
                "real degradation requirement",
            )
        for script in orphan:
            report.add(
                "B6_hook_degradation_coverage",
                "WARN",
                f"platforms/{plat_dir.name}",
                f"degradation entry {script!r} has no matching hooks.yaml "
                "script — dead config (silently outdated since the script "
                "was removed)",
            )


def _resolve_builtin_hook_dir() -> Path | None:
    """Locate the cataforge.hook.scripts package directory.

    ``importlib.resources.files`` returns a Traversable that's a real
    Path on filesystem-backed installs (editable + wheel). If the
    package is missing or zip-imported we fall back to None — the
    caller treats that as "no builtins available" and any script not
    in custom/ then fails reachability.
    """
    try:
        pkg = importlib.resources.files("cataforge.hook.scripts")
    except (ModuleNotFoundError, TypeError):
        return None
    p = Path(str(pkg))
    return p if p.is_dir() else None


def _resolve_hook_script(
    script: str,
    builtin_dir: Path | None,
    custom_dir: Path,
) -> Path | None:
    """Return the .py path for *script*, or None if not found.

    Mirrors the resolution logic in cataforge.hook.bridge so audit and
    deploy stay in lockstep — if this returns None, the deploy will
    also fail to wire the hook.
    """
    if script.startswith("custom:"):
        name = script.removeprefix("custom:")
        candidate = custom_dir / f"{name}.py"
        return candidate if candidate.is_file() else None
    if builtin_dir is None:
        return None
    candidate = builtin_dir / f"{script}.py"
    return candidate if candidate.is_file() else None


def _load_capability_ids() -> set[str]:
    """Return CAPABILITY_IDS ∪ EXTENDED_CAPABILITY_IDS, or empty on failure.

    Imports lazily so framework-review still runs on a project where
    cataforge.core.types isn't importable (e.g. older wheel) — the
    matcher_capability check just becomes a no-op.
    """
    try:
        from cataforge.core.types import CAPABILITY_IDS, EXTENDED_CAPABILITY_IDS
    except ImportError:
        return set()
    return set(CAPABILITY_IDS) | set(EXTENDED_CAPABILITY_IDS)


def run(
    scope: str,
    focus: list[str] | None,
    root: Path,
    meta_size_threshold: int,
) -> int:
    report = Report()

    enabled = set(focus) if focus else {"B1", "B2", "B3", "B4", "B5", "B6"}

    if "B1" in enabled and scope in ("agents", "skills", "rules", "all"):
        check_b1_required_sections(root, scope, report)
        check_b1_size(root, scope, meta_size_threshold, report)
    if "B2" in enabled and scope in ("agents", "skills", "all"):
        check_b2_cross_references(root, report)
    if "B3" in enabled and scope in ("skills", "all"):
        check_b3_manifest_drift(root, report)
    if "B4" in enabled and scope in ("agents", "skills", "rules", "all"):
        check_b4_hardcoded_constants(root, report)
    if "B5" in enabled and scope in ("workflow", "all"):
        check_b5_workflow_coverage(root, report)
    if "B6" in enabled and scope in ("hooks", "all"):
        check_b6_hook_consistency(root, report)

    print(f"framework-review scope={scope} focus={sorted(enabled)} root={root}")
    print("=" * 60)
    if not report.findings:
        print("No findings.")
        print("RESULT: PASS")
        return 0

    for f in report.findings:
        print(f.render())

    print()
    print("=" * 60)
    print(f"Summary: {report.fail_count} FAIL, {report.warn_count} WARN")
    if report.fail_count > 0:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS (warnings only)")
    return 0


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="CataForge framework meta-asset audit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "scope",
        choices=("agents", "skills", "hooks", "rules", "workflow", "all"),
        help="Asset scope to audit",
    )
    parser.add_argument(
        "--focus",
        default=None,
        help="Comma-separated subset of B1,B2,B3,B4,B5,B6",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Project root (default: walk up from cwd to find .cataforge/)",
    )
    parser.add_argument(
        "--meta-size-threshold",
        type=int,
        default=DEFAULT_META_SIZE,
        help="META_DOC_SPLIT_THRESHOLD_LINES override",
    )
    args = parser.parse_args()

    if args.root:
        root = Path(args.root).resolve()
    else:
        try:
            from cataforge.core.paths import find_project_root

            root = find_project_root()
        except Exception:
            root = Path.cwd()

    focus: list[str] | None = None
    if args.focus:
        focus = [c.strip() for c in args.focus.split(",") if c.strip()]
        invalid = [c for c in focus if c not in {"B1", "B2", "B3", "B4", "B5", "B6"}]
        if invalid:
            print(f"ERROR: invalid --focus values: {invalid}; expected B1..B6")
            sys.exit(2)

    # The `meta_size_threshold` could be loaded from framework.json
    # constants — tried below, but a non-fatal best-effort lookup.
    threshold = args.meta_size_threshold
    fw_json = root / ".cataforge" / "framework.json"
    if fw_json.is_file():
        try:
            data = json.loads(fw_json.read_text(encoding="utf-8"))
            v = (data.get("constants") or {}).get("META_DOC_SPLIT_THRESHOLD_LINES")
            if isinstance(v, int) and v > 0:
                threshold = v
        except (OSError, json.JSONDecodeError):
            pass

    sys.exit(run(args.scope, focus, root, threshold))


if __name__ == "__main__":
    main()
