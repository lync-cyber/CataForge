---
id: "dev-plan-lite-{project}"
version: "{ver}"
doc_type: dev-plan
author: tech-lead
status: draft
deps: ["arch-lite-{project}"]
consumers: [implementer, qa-engineer]
volume: main
mode: agile-lite
required_sections:
  - "## 1. 任务清单"
---
# Dev-Plan-Lite: {项目名称}

<!--
  Dev-Plan-Lite 适用于 agile-lite 执行模式。
  全文目标 ≤100 行；不产出 Sprint 分卷、依赖图、风险项表。
  任务粒度沿用 standard dev-plan 的"单次 Agent 调用可完成"原则。
  任务数建议 ≤25；若超出或依赖关系复杂，提示用户切换到 standard 模式。
-->

[NAV]
- §1 任务清单 → T-001..T-{NNN}
[/NAV]

## 1. 任务清单

### T-001: {任务名}
- **目标**: {一句话}
- **模块**: arch-lite-{project}#§2.M-001
- **task_kind**: feature  <!-- feature | fix | chore | config | docs；非 feature/fix 跳过 TDD -->
- **tdd_mode**: light
  <!-- agile-lite 默认 light；任务预估 LOC > TDD_LIGHT_LOC_THRESHOLD 或 security_sensitive 时升 standard -->
- **tdd_refactor**: auto  <!-- auto | required | skip；auto 按 TDD_REFACTOR_TRIGGER 条件触发 -->
- **security_sensitive**: false
- **tdd_acceptance**:
  - [ ] AC-001: Given {前置条件}, When {触发动作}, Then {可观测结果（具体返回值/状态变化/错误类型）}
  - [ ] AC-002: Given {前置条件}, When {触发动作}, Then {可观测结果}
- **deliverables**:
  - [ ] `src/{path}.py` — {功能实现}
  - [ ] `tests/{path}_test.py` — {测试}
- **context_load**:
  - arch-lite#§2.M-001
  - arch-lite#§3.API-001
- **依赖**: —

### T-002: {任务名}
- **目标**: ...
- **模块**: arch-lite-{project}#§2.M-002
- **task_kind**: feature
- **tdd_mode**: light
- **tdd_refactor**: auto
- **security_sensitive**: false
- **tdd_acceptance**:
  - [ ] AC-003: ...
- **deliverables**:
  - [ ] `src/...`
- **context_load**:
  - arch-lite#§2.M-002
- **依赖**: T-001
