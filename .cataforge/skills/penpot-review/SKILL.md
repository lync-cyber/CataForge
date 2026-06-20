---
name: penpot-review
description: "Penpot 设计 ↔ 代码一致性验证 — 比对 Penpot 设计与已实现代码的视觉一致性，产出差异报告与修复建议。当组件代码已实现且需要核对是否还原设计稿时使用此 skill。本 skill 专注 verification；代码骨架生成由 penpot-implement 负责，Token 同步由 penpot-sync 负责。"
argument-hint: "<component-id: UC-NNN 或代码文件路径>"
suggested-tools: file_read, file_glob, file_grep
depends: [context]
disable-model-invocation: false
user-invocable: true
---

# 设计-代码一致性验证 (penpot-review)
## 能力边界
- 能做: 比对Penpot设计与代码实现的视觉一致性、产出差异报告、建议修复方案
- 不做: 修改代码、修改设计、功能测试

## 前置条件
- {INSTRUCTION_FILE} `设计工具` 字段为 `penpot`
- Penpot MCP Server 已配置并可用
- 目标组件已有代码实现

## 输入规范
- Penpot 组件设计数据（通过 MCP 读取）
- 已实现的组件代码文件路径
- ui-spec#§2 中对应的 UC-{NNN} 规范（作为参考）

## 输出规范
- 设计一致性审查报告 `docs/reviews/design/DESIGN-REVIEW-{component_id}-r{N}.md`
- 差异列表（属性/值/偏差量）
- 修复建议

## 执行流程

### Step 1: 读取设计规范
- 通过 Penpot MCP 读取目标组件的完整设计属性:
  - 颜色值（背景/前景/边框）
  - 排版（字体/字号/行高/字重）
  - 间距（padding/margin/gap）
  - 尺寸（宽/高/边框圆角）
  - 布局方式（flex/grid/absolute）

### Step 2: 读取代码实现
- 从组件代码文件提取实际使用的样式值
- 解析 CSS/SCSS/CSS-in-JS 中的属性声明
- 识别 tokens.css 变量引用（标记为"通过Token间接匹配"）

### Step 3: 逐属性比对
对每个设计属性:
- 完全匹配 → PASS
- 通过Token匹配（值相同但来源不同）→ PASS（标注Token路径）
- 值不匹配 → DIFF（记录设计值 vs 代码值 vs 偏差量）
- 设计有但代码缺失 → MISSING
- 代码有但设计无 → EXTRA（仅记录，不视为问题）

### Step 4: 产出审查报告
格式:
```markdown
---
id: "design-review-{component_id}-r{N}"
doc_type: design-review
author: penpot-review
status: draft
deps: ["{component_id}"]
date: "{date}"
penpot: "{penpot_component_id}"
---

# DESIGN-REVIEW: {component_id}

## 一致性摘要
- 总属性数: {N}
- PASS: {N} | DIFF: {N} | MISSING: {N}
- 一致性得分: {百分比}%

## 差异详情
### [D-001] DIFF: {属性名}
- 设计值: {value}
- 代码值: {value}
- 偏差: {差异描述}
- 建议: {修复方案}
```

## Penpot MCP 工具发现
具体 MCP 工具名称以平台 MCP 配置为准（Claude: `.mcp.json` 或 `.claude/settings.json`；Cursor: `.cursor/mcp.json`；OpenCode: `opencode.json`），运行时通过可用工具列表自动发现。典型操作包括: 读取组件设计属性（颜色/排版/间距/尺寸/布局）。若工具列表中无 Penpot 相关工具，先运行 `cataforge penpot ensure` 尝试启动服务（若 Penpot 尚未部署则改运行 `cataforge penpot deploy`），仍不可用则返回 blocked。

## Anti-Patterns
- 禁止: 因 ≤1px 偏差直接判 DIFF —— 视觉对齐有亚像素噪声；<1px 标 WARN 而非 DIFF，否则审查噪音淹没真正偏差
- 禁止: 比对动画 / 交互 / 过渡属性 —— ui-spec 不承载交互契约；penpot-review 只对静态视觉，越界会引入大量假阳
- 禁止: 把 review 报告写到 docs/reviews/code/ 或 docs/reviews/doc/ —— 设计审查报告应入 docs/reviews/design/，混写让 sprint-review 聚合失真
- 避免: 把 Penpot 设计差异自动回写到 ui-spec —— 设计漂移修正必须经 ui-designer 显式判断，自动同步会让契约失去 reviewer 把关

## 效率策略
- 仅比对视觉相关属性，忽略交互/动画属性
- Token间接匹配视为通过，鼓励使用设计变量
- 小于1px的尺寸偏差标记为WARN而非DIFF
