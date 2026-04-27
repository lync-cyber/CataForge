---
id: "ui-spec-{project}-{ver}-theme-{NN}-{slug}"
doc_type: ui-spec
author: ui-designer
status: draft
deps: ["arch-{project}-{ver}-data"]
consumers: [tech-lead, developer]
volume: theme
volume_type: theme
split_from: "ui-spec-{project}-{ver}"
required_sections:
  - "## 4. 主题方案"
---
# UI Specification 分卷 — 主题方案: {主题名}

[NAV]
- §4 主题方案 → THEME-{NN}
[/NAV]

## 4. 主题方案

### 4.1 视觉语言
- **色彩**: {主色 / 辅色 / 中性色 token}
- **字体**: {正文 / 标题 / 代码字体}
- **间距与节奏**: {栅格、行高、留白比例}

### 4.2 适配组件
- 引用 [`ui-spec-{project}-{ver}-c{start}-c{end}`] 中的 C-XXX，列出主题覆写规则。

### 4.3 关键页面应用
- 引用 [`ui-spec-{project}-{ver}-p{start}-p{end}`] 中的 P-XXX，标注主题在该页的视觉表现。
