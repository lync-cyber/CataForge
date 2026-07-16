"""Static contract for the optional design-grill phase strategy."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from cataforge.runtime.skill.builtins.framework_review.framework_check import (
    Report,
    check_b2_cross_references,
)
from cataforge.utils.frontmatter import split_yaml_frontmatter

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".cataforge" / "skills"
GRILL = SKILLS / "design-grill" / "SKILL.md"
STAGE_SKILLS = ("req-analysis", "arc-design", "ui-design")
STAGE_AGENTS = ("product-manager", "architect", "ui-designer")
PROFILE_REFS = {
    "prd": SKILLS / "design-grill" / "references" / "prd.md",
    "arch": SKILLS / "design-grill" / "references" / "architecture.md",
    "ui": SKILLS / "design-grill" / "references" / "ui.md",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _body_and_meta() -> tuple[str, dict[str, object]]:
    meta, body = split_yaml_frontmatter(_read(GRILL), on_error="raise")
    assert meta is not None
    return body, meta


def _assert_terms(text: str, *terms: str) -> None:
    missing = [term for term in terms if term not in text]
    assert not missing, f"design-grill contract missing: {missing}"


def test_frontmatter_is_parseable_and_explicitly_gated() -> None:
    body, meta = _body_and_meta()

    assert meta["name"] == "design-grill"
    assert meta["argument-hint"] == "<prd|arch|ui> [需要深度澄清的范围]"
    assert set(meta["depends"]) == {"context", "research", "penpot-bridge"}
    assert meta["disable-model-invocation"] is False
    assert meta["user-invocable"] is True
    assert set(meta["suggested-tools"]) == {
        "file_read",
        "file_glob",
        "file_grep",
        "web_search",
        "web_fetch",
        "user_question",
    }
    _assert_terms(
        body,
        "默认关闭",
        "显式同意",
        "自动建议不等于启用",
        "阶段入口一次询问",
        "深度澄清(Grill)",
        "询问是协议动作",
    )


def test_stage_skills_are_the_only_default_callers() -> None:
    for skill_id in STAGE_SKILLS:
        text = _read(SKILLS / skill_id / "SKILL.md")
        meta, body = split_yaml_frontmatter(text, on_error="raise")
        assert meta is not None
        assert "design-grill" in meta["depends"]
        _assert_terms(body, "design-grill", "用户明确接受", "普通澄清")

    for agent_id in STAGE_AGENTS:
        text = _read(ROOT / ".cataforge" / "agents" / agent_id / "AGENT.md")
        meta, _ = split_yaml_frontmatter(text, on_error="raise")
        assert meta is not None
        assert "design-grill" not in meta["skills"]


def test_fact_first_decision_tree_and_question_contract() -> None:
    body, _ = _body_and_meta()
    _assert_terms(
        body,
        "本地事实优先",
        "不得再询问用户",
        "决策依赖树",
        "父决策未确认",
        "一次只问一个问题",
        "不构成过滤",
        "MAX_QUESTIONS_PER_BATCH",
        "推荐选项",
        "推荐依据",
        "主要代价或重评条件",
        "证据不足",
        "暂缓决定并先补事实",
    )


def test_controls_resume_and_convergence_contract() -> None:
    body, _ = _body_and_meta()
    _assert_terms(
        body,
        "接受建议",
        "接受本轮建议",
        "跳过",
        "暂停 Grill",
        "停止并总结",
        "继续 Grill",
        "不重问已解决问题",
        "共同理解",
        "完整收敛",
        "决定权在用户",
        "不自行宣布收敛",
        "决策无论大小都归用户",
    )


def test_prd_arch_and_ui_profiles_preserve_phase_boundaries() -> None:
    body, _ = _body_and_meta()
    _assert_terms(
        body,
        "按 scope 只加载一份",
        "references/prd.md",
        "references/architecture.md",
        "references/ui.md",
        "不得预加载其他 profile",
    )

    prd = _read(PROFILE_REFS["prd"])
    _assert_terms(
        prd,
        "# PRD Grill profile",
        "不讨论实现方案",
        "不得用现有实现替代产品意图",
        "Glossary",
    )

    arch = _read(PROFILE_REFS["arch"])
    _assert_terms(
        arch,
        "# Architecture Grill profile",
        "产品意图门",
        "交回 PRD",
        "难以逆转",
        "真实替代方案",
        "ADR-NNN",
    )

    ui = _read(PROFILE_REFS["ui"])
    _assert_terms(
        ui,
        "# UI Grill profile",
        "交回 Arch",
        "语义契约始终归 UI-SPEC",
        "penpot-bridge `read`",
        "不得调用 `generate` 或 `verify`",
    )


def test_modes_and_evidence_lifecycle_contract() -> None:
    body, _ = _body_and_meta()
    _assert_terms(
        body,
        "standard",
        "agile-lite",
        "agile-prototype",
        "不自动建议 Grill",
        "research-note",
        "过程证据",
        "阶段文档是终态权威",
        "每个阶段的一次连续 Grill 会话最多维护一份",
        "[ASSUMPTION]",
    )


def test_summary_contract_is_traceable() -> None:
    body, _ = _body_and_meta()
    _assert_terms(
        body,
        "本次范围",
        "已确认决策",
        "已核实本地事实",
        "假设清单",
        "owner",
        "术语变化",
        "ADR 候选",
        "章节映射",
        "确认总结并恢复阶段流程",
    )


def test_no_new_phase_config_or_formal_doc_type() -> None:
    framework = json.loads(_read(ROOT / ".cataforge" / "framework.json"))
    phases = {
        phase["phase"]
        for mode in framework["workflow"]["modes"].values()
        for phase in mode["phases"]
    }
    assert "grill" not in phases
    assert "design_grill" not in framework

    registry = yaml.safe_load(_read(SKILLS / "context" / "templates" / "_registry.yaml"))
    assert "design-grill" not in registry["templates"]
    assert all(item["doc_type"] != "design-grill" for item in registry["templates"].values())


def test_b2_graph_has_no_design_grill_findings() -> None:
    report = Report()
    check_b2_cross_references(ROOT, report)
    findings = [
        finding
        for finding in report.findings
        if "design-grill" in f"{finding.location} {finding.message}"
    ]
    assert findings == []


def test_skill_count_and_user_facing_docs_are_28() -> None:
    actual = sum(1 for path in SKILLS.iterdir() if path.is_dir() and (path / "SKILL.md").is_file())
    assert actual == 28

    claims = {
        ROOT / "README.md": r"28\s*个\s*Skill",
        ROOT / "docs" / "README.md": r"\+\s*28\s*个\s*Skill",
        ROOT / "docs" / "reference" / "agents-and-skills.md": (r"Skill\s*清单（\s*28\s*个\s*）"),
    }
    for path, pattern in claims.items():
        assert re.search(pattern, _read(path)), f"count missing from {path}"
