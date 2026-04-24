---
id: "ui-spec-lite-{project}-{ver}"
doc_type: ui-spec
author: ui-designer
status: draft
deps: ["prd-lite-{project}-{ver}"]
consumers: [tech-lead, implementer]
volume: main
mode: agile-lite
required_sections:
  - "## 1. 设计系统"
  - "## 2. 组件清单"
---
# UI Specification-Lite: {项目名称}

<!--
  UI-Spec-Lite 适用于 agile-lite 执行模式。
  全文目标 ≤100 行；仅记录设计系统核心 Token 和主要组件，不需要 §0 设计方向、页面布局、导航路由、响应式策略。
  若内容在 150 行内仍无法表达清楚核心 UI 规范，提示用户切换到 standard 模式。
-->

[NAV]
- §1 设计系统 → §1.1 色彩, §1.2 排版, §1.3 间距与圆角
- §2 组件清单 → C-001..C-{NNN}
[/NAV]

## 1. 设计系统

### 1.1 色彩
<!-- agile-lite 要求至少 3 个 Token：主色、语义色（success/error 之一）、中性色 -->
| Token名 | 值 | 用途 |
|---------|------|------|
| color-primary | #{HEX} | 主色 / 强调色 |
| color-danger | #{HEX} | 错误 / 警告 |
| color-neutral | #{HEX} | 文字 / 边框 |

**对比度**: 正文与背景对比度≥4.5:1。

### 1.2 排版
| Token名 | 值 | 用途 |
|---------|------|------|
| font-base | {如 14px / 1.5} | 正文 |
| font-heading | {如 20px / 1.3 bold} | 标题 |

### 1.3 间距与圆角
| Token名 | 值 | 用途 |
|---------|------|------|
| space-unit | {如 4px} | 基础间距单位 |
| radius-base | {如 6px} | 默认圆角 |

## 2. 组件清单

### C-001: {组件名}
- **变体**: default, hover, disabled
- **视觉差异**: {各状态的关键视觉变化，如 hover 背景加深 8%、disabled opacity 0.5}
- **Props**: { label: string, onClick: fn, disabled?: bool }
- **映射功能**: F-001 (引用 prd-lite)

### C-002: {组件名}
- **变体**: ...
- **视觉差异**: ...
- **Props**: ...
- **映射功能**: F-002
