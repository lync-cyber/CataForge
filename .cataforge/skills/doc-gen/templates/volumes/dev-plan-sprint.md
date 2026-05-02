---
id: "dev-plan-{project}-s{N}"
version: "{ver}"
doc_type: dev-plan
author: tech-lead
status: draft
deps: ["arch-{project}", "ui-spec-{project}"]
consumers: [developer, qa-engineer]
volume: sprint
volume_type: sprint
split_from: "dev-plan-{project}"
required_sections:
  - "## 3. 任务卡详细"
---
# Development Plan 分卷 — Sprint {N}: {项目名称}

[NAV]
- §3 任务卡详细 → T-{start}..T-{end} (Sprint {N})
[/NAV]

## 3. 任务卡详细

### T-{start}: {任务名}
- **目标**: {一句话描述任务目标}
- **模块**: M-001
- **接口**: API-001
- **tdd_acceptance**:
  - [ ] AC-001: {测试描述} → 预期: {结果}
  - [ ] AC-002: {测试描述} → 预期: {结果}
- **deliverables** (交付物):
  - [ ] `src/module-a/feature_x.py` — {功能模块实现}
  - [ ] `tests/module-a/test_feature_x.py` — {单元测试}
- **context_load**: (doc-nav加载清单)
  - arch#§2.M-001
  - arch-api#API-001
  - arch-data#E-001
- **实现提示**: {关键技术点, 仅在必要时}

### T-{start+1}: {任务名}
...
