"""L1 — Prompt 快照测试 (P0-3 Step 1)

目的: 固化 orchestrator 启动时看到的系统 prompt 组合 + 每次 agent-dispatch
生成的子代理 prompt，任何对 AGENT.md / SKILL.md / COMMON-RULES.md / dispatch-prompt.md
的无意修改都会在 diff 中暴露。

设计理念:
  - 不调用任何 LLM API，纯文本组合，零成本。
  - 快照存于 tests/snapshots/*.txt，首次运行自动生成；后续改动需显式提交更新。
  - 组合逻辑模拟 Claude Code 实际加载顺序: CLAUDE.md + COMMON-RULES.md + AGENT.md
    + dispatch prompt 模板（其中 {占位符} 替换为固定示例值以保证确定性）。

更新快照的方法:
  SNAPSHOT_UPDATE=1 uv run python -m pytest tests/test_prompt_snapshot.py

失败时的检查路径:
  1. 对比 diff，确认变更是预期的文档/模板修订
  2. 若预期，更新快照; 若非预期，审查是否有意外内容流入
"""

from __future__ import annotations

import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "snapshots")
AGENTS_DIR = os.path.join(PROJECT_ROOT, ".claude", "agents")
SKILLS_DIR = os.path.join(PROJECT_ROOT, ".claude", "skills")
RULES_DIR = os.path.join(PROJECT_ROOT, ".claude", "rules")
DISPATCH_TEMPLATE = os.path.join(
    SKILLS_DIR, "agent-dispatch", "templates", "dispatch-prompt.md"
)
CLAUDE_MD = os.path.join(PROJECT_ROOT, "CLAUDE.md")
COMMON_RULES = os.path.join(RULES_DIR, "COMMON-RULES.md")
SUB_AGENT_PROTOCOLS = os.path.join(RULES_DIR, "SUB-AGENT-PROTOCOLS.md")
ORCHESTRATOR_PROTOCOLS = os.path.join(
    AGENTS_DIR, "orchestrator", "ORCHESTRATOR-PROTOCOLS.md"
)


# ============================================================================
# 辅助: 文件读取 + 占位符归一化
# ============================================================================


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _normalize_volatile(text: str) -> str:
    """归一化易变字段（版本号、时间戳），避免与内容无关的快照漂移。"""
    # pyproject 版本号行
    text = re.sub(
        r'^version\s*=\s*"[^"]+"',
        'version = "<NORMALIZED>"',
        text,
        flags=re.MULTILINE,
    )
    # CLAUDE.md 框架版本字段
    text = re.sub(
        r"(框架版本:\s*)(\S+)",
        lambda m: f"{m.group(1)}<NORMALIZED>",
        text,
    )
    return text


def _combine_system_prompt(agent_id: str) -> str:
    """模拟 orchestrator/子代理会话启动时加载的系统 prompt 组合。

    顺序（与 Claude Code 实际加载一致）:
      1. CLAUDE.md (project instructions)
      2. COMMON-RULES.md (project instructions)
      3. AGENTS/{agent_id}/AGENT.md
      4. （orchestrator 独有）ORCHESTRATOR-PROTOCOLS.md
      5. SUB-AGENT-PROTOCOLS.md (所有子代理共享)
    """
    parts: list[str] = []
    parts.append("=== CLAUDE.md ===")
    parts.append(_read(CLAUDE_MD))
    parts.append("=== COMMON-RULES.md ===")
    parts.append(_read(COMMON_RULES))

    agent_md = os.path.join(AGENTS_DIR, agent_id, "AGENT.md")
    if os.path.exists(agent_md):
        parts.append(f"=== {agent_id}/AGENT.md ===")
        parts.append(_read(agent_md))

    if agent_id == "orchestrator":
        parts.append("=== ORCHESTRATOR-PROTOCOLS.md ===")
        parts.append(_read(ORCHESTRATOR_PROTOCOLS))
    else:
        parts.append("=== SUB-AGENT-PROTOCOLS.md ===")
        parts.append(_read(SUB_AGENT_PROTOCOLS))

    combined = "\n\n".join(parts)
    return _normalize_volatile(combined)


def _render_dispatch_prompt(agent_id: str, task_type: str = "new_creation") -> str:
    """渲染 agent-dispatch 模板，用固定占位符值替换变量部分。"""
    template = _read(DISPATCH_TEMPLATE)
    substitutions = {
        "{agent_id}": agent_id,
        "{N}": "2",
        "{简短描述}": "示例任务",
        "{项目名}": "SNAPSHOT-EXAMPLE",
        "{task}": "为快照测试构造的示例任务",
        "{task_type}": task_type,
        "{input_docs}": "docs/prd/prd-example-v1.md",
        "{expected_output}": "docs/arch/arch-example-v1.md",
        "{review_path}": "docs/reviews/doc/REVIEW-prd-example-v1-r1.md",
        "{answers}": "Q1: 示例问题 → A: 示例回答",
        "{intermediate_outputs}": "docs/arch/arch-example-v1.md",
        "{resume_guidance}": "从 Step 3 继续",
        "{change_analysis}": "<change-analysis>...</change-analysis>",
        "{change_description}": "添加 OAuth 登录",
        "{category}": "completeness",
        "{问题描述}": "示例问题描述",
    }
    rendered = template
    for k, v in substitutions.items():
        rendered = rendered.replace(k, v)
    return rendered


# ============================================================================
# 快照 I/O
# ============================================================================


def _snapshot_path(name: str) -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    return os.path.join(SNAPSHOT_DIR, f"{name}.txt")


def _assert_snapshot(name: str, actual: str) -> None:
    """比对快照。SNAPSHOT_UPDATE=1 时覆写；否则严格比对。"""
    path = _snapshot_path(name)
    update = os.environ.get("SNAPSHOT_UPDATE") == "1"

    if update or not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(actual)
        if not os.path.exists(path):
            pytest.skip(f"快照创建: {path}")
        return

    with open(path, "r", encoding="utf-8") as f:
        expected = f.read()

    if expected != actual:
        # 输出前 30 行 diff 方便诊断
        import difflib

        diff = list(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile=f"{name} (expected)",
                tofile=f"{name} (actual)",
                lineterm="",
                n=3,
            )
        )
        msg = (
            f"快照漂移: {name}\n"
            f"如变更符合预期，运行 SNAPSHOT_UPDATE=1 uv run python -m pytest "
            f"tests/test_prompt_snapshot.py 更新\n\n"
            + "\n".join(diff[:80])
        )
        pytest.fail(msg)


# ============================================================================
# 测试用例
# ============================================================================


def _discover_agents() -> list[str]:
    if not os.path.exists(AGENTS_DIR):
        return []
    return sorted(
        d
        for d in os.listdir(AGENTS_DIR)
        if os.path.isdir(os.path.join(AGENTS_DIR, d))
        and os.path.exists(os.path.join(AGENTS_DIR, d, "AGENT.md"))
    )


@pytest.mark.parametrize("agent_id", _discover_agents())
def test_system_prompt_snapshot(agent_id: str) -> None:
    """每个 agent 启动时看到的系统 prompt 组合必须稳定。"""
    combined = _combine_system_prompt(agent_id)
    _assert_snapshot(f"system_prompt_{agent_id}", combined)


@pytest.mark.parametrize("task_type", ["new_creation", "revision", "continuation", "amendment"])
def test_dispatch_prompt_snapshot(task_type: str) -> None:
    """每种 task_type 渲染出的 dispatch prompt 必须稳定。"""
    rendered = _render_dispatch_prompt("architect", task_type=task_type)
    _assert_snapshot(f"dispatch_prompt_{task_type}", rendered)


def test_dispatch_template_contains_required_sections() -> None:
    """dispatch 模板必须包含 agent-result XML 块、task_type、COMMON-SECTIONS 标记。"""
    template = _read(DISPATCH_TEMPLATE)
    assert "<agent-result>" in template, "缺少 agent-result XML 起始标签"
    assert "</agent-result>" in template, "缺少 agent-result XML 结束标签"
    assert "{task_type}" in template, "缺少 task_type 占位符"
    assert "BEGIN COMMON-SECTIONS" in template, "缺少 COMMON-SECTIONS 起始标记"
