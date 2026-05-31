---
id: "arch-{project}-modules"
version: "{ver}"
doc_type: arch
author: architect
status: draft
deps: ["prd-{project}"]
consumers: [tech-lead, developer, devops]
volume: modules
volume_type: modules
split_from: "arch-{project}"
required_sections:
  - "## 2. 模块划分"
---
# Architecture 分卷 — 模块划分: {项目名称}

[NAV]
- §2 模块划分 → M-001..M-{NNN}
[/NAV]

## 2. 模块划分

### M-001: {模块名称}
- **职责**: {单一职责描述}
- **映射功能**: F-001, F-003 (引用PRD)
- **对外接口**: API-001, API-002 (引用接口分卷)
- **依赖模块**: M-002, M-005
- **内部关键组件**: {类/组件列表}

### M-002: {模块名称}
...
