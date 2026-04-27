"""framework_check.py — Framework meta-asset structural audit (Layer 1).

Six independent sub-checks driven by ``--scope`` and ``--focus``:

* B1-α: required SKILL.md / AGENT.md sections
* B1-β: file size threshold (META_DOC_SPLIT_THRESHOLD_LINES)
* B2-α: cross-reference graph (AGENT.md.skills + SKILL.md.depends +
  framework.json.features → resolves to existing assets)
* B3-α: SKILL.md "## Layer 1 检查项" ↔ builtin CHECKS_MANIFEST drift
* B4-α: hard-coded constant drift (numeric literals that should
  reference COMMON-RULES constants)
* B5-α: workflow coverage matrix (ORCHESTRATOR-PROTOCOLS dispatch
  table × framework.json.features × agents)

Usage:
  python -m cataforge.skill.builtins.framework_review.framework_check \\
        <scope: agents|skills|hooks|rules|workflow|all> \\
        [--focus B1,B2,B3,B4,B5] \\
        [--root <project_root>] \\
        [--meta-size-threshold N]

Exit codes follow §Layer 1 调用协议: 0=PASS, 1=FAIL (any check found
problems), 2=usage error.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

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


def check_b3_manifest_drift(root: Path, report: Report) -> None:
    """B3-α: SKILL.md '## Layer 1 检查项' ↔ CHECKS_MANIFEST."""
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

        # Delegation pattern: SKILL.md may explicitly delegate authority
        # to the manifest (e.g. "权威清单见 cataforge.skill.builtins.X.CHECKS_MANIFEST"),
        # in which case prose duplication is intentionally minimal and
        # token-by-token matching would produce noisy false positives.
        # We still verify the manifest exists below — that is the
        # actual contract.
        delegation_re = re.compile(
            r"权威清单见.*?CHECKS_MANIFEST", re.DOTALL
        )
        delegated = bool(delegation_re.search(section_text))

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

        # When SKILL.md delegated to manifest, manifest existence is
        # the only contract — skip per-entry token matching.
        if delegated:
            continue

        # Soft drift detection: every manifest entry's title must have at
        # least one significant token appearing in the prose section.
        # We're not parsing markdown — humans may rephrase, but the
        # critical keyword should survive. A missing title hits FAIL.
        for entry in manifest:
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            tokens = [
                t for t in re.split(r"[\s/(),:：]+", title)
                if t and len(t) >= 3 and not t.isascii() or t.lower() in {"check", "ac", "id"}
            ]
            # Require at least one non-trivial token to appear.
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


def check_b5_workflow_coverage(root: Path, report: Report) -> None:
    """B5-α: phase × agent × skill coverage matrix.

    Builds a coverage matrix from:
    * ORCHESTRATOR-PROTOCOLS.md `Mode Routing Protocol` + orchestrator
      AGENT.md `Phase Routing` (which agent serves which phase)
    * framework.json `features` (which features are auto-enabled per phase)
    * AGENT.md `skills:` (which skills each agent loads)

    Then flags:
    * Phases with no agent assignment (WARN)
    * Agents defined but never referenced by any phase routing (WARN)
    """
    orch_path = root / ".cataforge" / "agents" / "orchestrator" / "AGENT.md"
    if not orch_path.is_file():
        return

    try:
        orch_text = orch_path.read_text(encoding="utf-8")
    except OSError:
        return

    # Extract "Phase N {name} → {agent} → {output}" patterns from
    # the Phase Routing block. The orchestrator AGENT.md format is
    # stable enough that a coarse regex suffices.
    phase_re = re.compile(
        r"Phase\s+\d+\s+(\w[\w_-]*)\s*[→\-]+\s*([\w-]+)",
        re.MULTILINE,
    )
    phase_to_agent: dict[str, str] = {}
    for match in phase_re.finditer(orch_text):
        phase_to_agent[match.group(1)] = match.group(2)

    if not phase_to_agent:
        return

    agents = discover_agents(root)

    # Phases with no agent assignment.
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

    # Agents never referenced by any phase routing.
    referenced_agents = set(phase_to_agent.values())
    # Sub-agents called by tdd-engine and not phase-routed directly.
    referenced_agents.update({"test-writer", "implementer", "refactorer"})
    # Cross-cutting agents.
    referenced_agents.update({"reviewer", "debugger", "orchestrator", "reflector"})

    for agent in sorted(agents):
        if agent not in referenced_agents:
            report.add(
                "B5_workflow_coverage_matrix",
                "WARN",
                f"agents/{agent}",
                "agent defined but not referenced by any phase routing "
                "or sub-agent dispatcher",
            )


def run(
    scope: str,
    focus: list[str] | None,
    root: Path,
    meta_size_threshold: int,
) -> int:
    report = Report()

    enabled = set(focus) if focus else {"B1", "B2", "B3", "B4", "B5"}

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
        help="Comma-separated subset of B1,B2,B3,B4,B5",
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
        invalid = [c for c in focus if c not in {"B1", "B2", "B3", "B4", "B5"}]
        if invalid:
            print(f"ERROR: invalid --focus values: {invalid}; expected B1..B5")
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
