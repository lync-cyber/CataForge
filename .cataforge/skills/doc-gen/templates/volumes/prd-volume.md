---
id: "prd-{project}-f{start}-f{end}"
version: "{ver}"
doc_type: prd
author: product-manager
status: draft
deps: []
consumers: [architect, ui-designer, tech-lead]
volume: features
volume_type: features
split_from: "prd-{project}"
required_sections:
  - "## 2. 功能需求"
---
# PRD 分卷 — 功能需求: {项目名称}

[NAV]
- §2 功能需求 → F-{start}..F-{end}
[/NAV]

## 2. 功能需求

### F-{start}: {功能名称}
- **用户故事**: 作为{角色}，我希望{动作}，以便{价值}
- **验收标准**:
  - [ ] AC-001: {可验证的条件}
  - [ ] AC-002: {可验证的条件}
- **优先级**: P0/P1/P2
- **备注**: {约束/边界条件/[ASSUMPTION]标注}

### F-{start+1}: {功能名称}
...
