---
id: "dev-plan-lite-{project}-{ver}"
doc_type: dev-plan
author: tech-lead
status: draft
deps: ["arch-lite-{project}-{ver}"]
consumers: [implementer, qa-engineer]
volume: main
mode: agile-lite
required_sections:
  - "## 1. 任务清单"
---
# Dev-Plan-Lite: {项目名称}

<!--
  Dev-Plan-Lite 适用于 agile-lite 执行模式。
  全文目标 ≤50 行；不产出 Sprint 分卷、依赖图、风险项表。
  任务粒度沿用 standard dev-plan 的"单次 Agent 调用可完成"原则。
-->

[NAV]
- §1 任务清单 → T-001..T-{NNN}
[/NAV]

## 1. 任务清单

### T-001: {任务名}
- **目标**: {一句话}
- **模块**: M-001
- **tdd_mode**: light
  <!-- agile-lite 默认 light；若任务预估 LOC ≥ TDD_LIGHT_LOC_THRESHOLD 可标 standard -->
- **tdd_acceptance**:
  - [ ] AC-001: {测试描述} → 预期: {结果}
  - [ ] AC-002: {测试描述} → 预期: {结果}
- **deliverables**:
  - [ ] `src/{path}.py` — {功能实现}
  - [ ] `tests/{path}_test.py` — {测试}
- **context_load**:
  - arch-lite#§2.M-001
  - arch-lite#§3.API-001
- **依赖**: —

### T-002: {任务名}
- **目标**: ...
- **模块**: M-002
- **tdd_mode**: light
- **tdd_acceptance**:
  - [ ] AC-003: ...
- **deliverables**:
  - [ ] `src/...`
- **context_load**:
  - arch-lite#§2.M-002
- **依赖**: T-001
