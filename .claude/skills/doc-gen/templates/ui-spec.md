# UI Specification: {项目名称}
<!-- required_sections: ["## 1. 设计系统", "## 2. 组件清单", "## 3. 页面布局"] -->
<!-- id: ui-spec-{project}-{ver} | author: ui-designer | status: draft -->
<!-- deps: prd-{project}-{ver}, arch-{project}-{ver} | consumers: tech-lead, developer -->
<!-- volume: main -->

[NAV]
- §1 设计系统 → §1.1 色彩, §1.2 排版, §1.3 间距
- §2 组件清单 → C-001..C-{NNN}
- §3 页面布局 → P-001..P-{NNN}
- §4 导航与路由
- §5 响应式策略
[/NAV]

## 1. 设计系统
### 1.1 色彩
| Token名 | 值 | 用途 |
|---------|------|------|

### 1.2 排版
| Token名 | 值 | 用途 |
|---------|------|------|

### 1.3 间距与栅格
{间距系统}

## 2. 组件清单
### C-001: {组件名}
- **变体**: default, hover, active, disabled, error
- **Props**: { label: string, onClick: fn, disabled?: bool }
- **映射功能**: F-001 (引用PRD)
- **交互说明**: {关键交互}

## 3. 页面布局
### P-001: {页面名}
- **路由**: /path
- **使用组件**: C-001, C-003
- **布局描述**: {线框描述}
- **状态流**: loading → empty → populated → error
- **映射功能**: F-001, F-002

## 4. 导航与路由
| 路由 | 页面 | 权限 |
|------|------|------|

## 5. 响应式策略
| 断点 | 宽度 | 布局变化 |
|------|------|----------|