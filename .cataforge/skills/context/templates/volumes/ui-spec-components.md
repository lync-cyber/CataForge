---
id: "ui-spec-{project}-c{start}-c{end}"
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
- §2 组件清单 → C-{start}..C-{end}
[/NAV]

## 2. 组件清单

### C-{start}: {组件名}
- **变体**: default, hover, active, disabled, error
- **视觉差异**: {各状态的视觉变化描述，如hover时背景色加深10%、disabled时opacity: 0.5}
- **Props**: { label: string, onClick: fn, disabled?: bool }
- **映射功能**: F-001 (引用PRD)
- **交互说明**: {关键交互行为和反馈方式}

### C-{start+1}: {组件名}
...
