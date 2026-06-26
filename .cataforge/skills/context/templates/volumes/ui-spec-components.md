---
id: "ui-spec-{project}-uc{start}-uc{end}"
version: "{ver}"
doc_type: ui-spec
author: ui-designer
status: draft
deps: ["prd-{project}", "arch-{project}"]
consumers: [tech-lead, developer]
volume: components
volume_type: components
split_from: "ui-spec-{project}"
required_sections:
  - "## 2. 组件清单"
---
# UI Specification 分卷 — 组件清单: {项目名称}

[NAV]
- §2 组件清单 → UC-{start}..UC-{end}
[/NAV]

<!-- 权威源（design_tool=penpot 时）：UC 身份/Props/状态枚举/功能映射以 ui-spec 为权威源；视觉值（尺寸/真实 CSS/层级几何）随 authoring surface（doc-first 默认 ui-spec 权威；Penpot-first 取 Penpot、本卷存派生快照）。design_tool=none 时本卷即权威源。 -->

## 2. 组件清单

### UC-{start}: {组件名}
- **变体**: default, hover, active, disabled, error
- **视觉差异**: {各状态的视觉变化描述，如hover时背景色加深10%、disabled时opacity: 0.5}
- **Props**: { label: string, onClick: fn, disabled?: bool }
- **映射功能**: F-001 (引用PRD)
- **交互说明**: {关键交互行为和反馈方式}

### UC-{start+1}: {组件名}
...
