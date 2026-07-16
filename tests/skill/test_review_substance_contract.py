"""Static contract: doc-review / code-review Layer 2 anchor on substance, not form."""

from __future__ import annotations

import re
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine.registry import CATEGORIES

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / ".cataforge" / "skills" / "context" / "references" / "review.md"
CODE_REVIEW_SKILL = ROOT / ".cataforge" / "skills" / "code-review" / "SKILL.md"
COMMON_RULES = ROOT / ".cataforge" / "rules" / "COMMON-RULES.md"
PROFILE_REFS = {
    "prd": REVIEW.parent / "review-prd.md",
    "arch": REVIEW.parent / "review-arch.md",
    "ui-spec": REVIEW.parent / "review-ui-spec.md",
}

# Layer 1 has dedicated categories beyond the COMMON-RULES taxonomy table.
LAYER1_ONLY_CATEGORIES = {"integration-wiring", "visual-fidelity", "arch"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_terms(text: str, *terms: str) -> None:
    missing = [term for term in terms if term not in text]
    assert not missing, f"substance contract missing: {missing}"


def test_doc_review_layer2_owns_substance_not_form() -> None:
    text = _read(REVIEW)
    _assert_terms(
        text,
        "双层分工契约",
        "Layer 1 独占",
        "不复报可机检问题",
        "实质维度",
        "不按形式醒目程度定级",
    )
    # 规范性 belongs to Layer 1; it must not reappear in the Layer 2 dimension list
    # (scoped to the dimension line so prose mentioning the word stays legal).
    dimension_lines = [ln for ln in text.splitlines() if "通用维度" in ln]
    assert dimension_lines, "通用维度行缺失"
    assert all("规范性" not in ln for ln in dimension_lines)
    assert "完整性 / 一致性 / 可行性 / 安全性 / 清晰度" in text


def test_doc_review_routes_one_profile_per_doc_type() -> None:
    text = _read(REVIEW)
    _assert_terms(
        text,
        "只加载对应单份 profile",
        "review-prd.md",
        "review-arch.md",
        "review-ui-spec.md",
        "严重度锚点",
    )
    for doc_type, path in PROFILE_REFS.items():
        assert path.is_file(), f"missing profile for {doc_type}: {path.name}"


def test_profiles_carry_substance_dimensions_and_severity_anchors() -> None:
    for path in PROFILE_REFS.values():
        text = _read(path)
        _assert_terms(text, "实质审查 profile", "假设设计存在缺陷", "## 实质维度", "## 严重度锚点")
        assert "差:" in text and "好:" in text, f"{path.name} 缺少做A而非B对比锚点"

    prd = _read(PROFILE_REFS["prd"])
    _assert_terms(prd, "失败路径", "可用闭环", "可证伪", "P0 膨胀", "[ASSUMPTION]")

    arch = _read(PROFILE_REFS["arch"])
    _assert_terms(arch, "真实备选", "承载模块", "降级", "过度设计", "信任边界")

    ui = _read(PROFILE_REFS["ui-spec"])
    _assert_terms(
        ui,
        "loading / empty / populated / error",
        "死 token",
        "不以视觉设计掩盖上游缺口",
        "保真类 AC",
    )


def test_code_review_dimensions_are_substance_first() -> None:
    text = _read(CODE_REVIEW_SKILL)
    _assert_terms(
        text,
        "功能正确性(correctness)",
        "不以测试绿等价",
        "性能(performance)",
        "排序即注意力优先级",
        "Layer 1 lint 机检面不复报",
    )
    correctness = text.index("- 功能正确性(correctness)")
    convention = text.index("- 命名规范(convention)")
    assert correctness < convention, "correctness 维度必须排在 convention 之前"


def test_systemic_clustering_escalation_contract() -> None:
    rules = _read(COMMON_RULES)
    _assert_terms(
        rules,
        "REVIEW_SYSTEMIC_MEDIUM_THRESHOLD",
        "聚类升级",
        "系统性 HIGH",
        "members",
        "密度不裸计数",
    )
    import json

    framework = json.loads(_read(ROOT / ".cataforge" / "framework.json"))
    assert framework["constants"]["REVIEW_SYSTEMIC_MEDIUM_THRESHOLD"] == 5

    reviewer = _read(ROOT / ".cataforge" / "agents" / "reviewer" / "AGENT.md")
    _assert_terms(
        reviewer,
        "聚类升级",
        "无①产生的系统性 HIGH",
        "操纵聚类计数",
    )


def test_revision_piggyback_and_notes_lifecycle_contract() -> None:
    protocols = _read(ROOT / ".cataforge" / "rules" / "SUB-AGENT-PROTOCOLS.md")
    _assert_terms(
        protocols,
        "必须修复全部 CRITICAL 和 HIGH",
        "同文件/同节内的 MEDIUM/LOW 顺带一并修复",
        "不为其扩大修改面",
    )
    _assert_terms(_read(REVIEW), "still-open", "参与本轮聚类升级计数")
    _assert_terms(_read(CODE_REVIEW_SKILL), "still-open", "参与本轮聚类升级计数")


def test_category_taxonomy_is_synced_between_rules_and_registry() -> None:
    assert "correctness" in CATEGORIES

    table = re.search(
        r"## 统一问题分类体系.*?(?=^## )", _read(COMMON_RULES), re.DOTALL | re.MULTILINE
    )
    assert table is not None
    rows = set(re.findall(r"^\| ([a-z-]+) \|", table.group(0), re.MULTILINE)) - {"category"}
    assert "correctness" in rows
    registry_only = sorted(CATEGORIES - LAYER1_ONLY_CATEGORIES - rows)
    assert rows == CATEGORIES - LAYER1_ONLY_CATEGORIES, (
        "COMMON-RULES §统一问题分类体系 与 registry.CATEGORIES 漂移: "
        f"仅表中={sorted(rows - CATEGORIES)} 仅注册表={registry_only}"
    )
