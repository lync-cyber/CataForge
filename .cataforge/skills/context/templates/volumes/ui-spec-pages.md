---
id: "ui-spec-{project}-p{start}-p{end}"
version: "{ver}"
doc_type: ui-spec
author: ui-designer
status: draft
deps: ["prd-{project}", "arch-{project}"]
consumers: [tech-lead, developer]
volume: pages
volume_type: pages
split_from: "ui-spec-{project}"
required_sections:
  - "## 3. 页面布局"
---
# UI Specification 分卷 — 页面布局: {项目名称}

[NAV]
- §3 页面布局 → P-{start}..P-{end}
[/NAV]

## 3. 页面布局

### P-{start}: {页面名}
- **路由**: /path
- **使用组件**: C-001, C-003
- **空间构成**: {视觉重心位置、密集区/留白区分布、关键间距}
- **布局描述**: {区域划分、组件排列方式，足以让开发者还原}
- **状态流**:
  - loading: {具体表现，如骨架屏/加载动画}
  - empty: {引导文案和视觉元素}
  - populated: {正常数据展示}
  - error: {错误提示样式和恢复操作}
- **映射功能**: F-001, F-002

### P-{start+1}: {页面名}
...
