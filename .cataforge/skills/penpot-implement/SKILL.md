---
name: penpot-implement
description: "Penpot 组件代码生成 — 从 Penpot 设计组件读取结构/样式/属性，生成前端组件代码骨架。当 ui-spec 已定义 C-{NNN} 组件且需要从设计稿落地代码骨架时使用此 skill。本 skill 专注 generation；设计 ↔ 代码一致性验证由 penpot-review 负责，Token 双向同步由 penpot-sync 负责。"
argument-hint: "<component-id: C-NNN 或 Penpot组件名>"
suggested-tools: Read, Write, Edit, Glob, Grep
depends: [doc-nav, penpot-sync]
disable-model-invocation: false
user-invocable: true
---

# Penpot组件代码生成 (penpot-implement)
## 能力边界
- 能做: 从Penpot组件读取结构/样式/属性、生成组件代码骨架
- 不做: 完整业务逻辑实现、状态管理、API对接、设计-代码一致性验证（由 penpot-review 负责）、Token 同步（由 penpot-sync 负责）

## 前置条件
- CLAUDE.md `设计工具` 字段为 `penpot`
- Penpot MCP Server 已配置并可用
- ui-spec 中对应的 C-{NNN} 规范已定义

## 输入规范
- ui-spec#§2 组件目录中的 C-{NNN}（Props/变体/交互描述）
- arch#§1.4 技术栈（确定生成 React/Vue/HTML 格式）
- Penpot 中对应组件的设计数据（通过 MCP 读取）

## 输出规范
- 组件代码骨架文件（按 arch 技术栈格式）
- 组件样式文件（引用 tokens.css 变量）

> 一致性比对不在本 skill 输出之内：生成骨架后若需验证还原度，由 orchestrator 调度 penpot-review 接管。

## 执行流程

### Step 1: 加载上下文
- 通过 doc-nav 加载 ui-spec 中目标 C-{NNN} 的完整规范
- 通过 doc-nav 加载 arch#§1.4 确定技术栈（React/Vue/HTML等）
- 通过 Penpot MCP 读取对应组件的设计数据（结构/CSS/SVG）

### Step 2: 解析 Penpot 组件
- 提取组件层级结构（容器/子元素/文本/图标）
- 提取 CSS 属性（尺寸/颜色/字体/间距/边框）
- 映射到 tokens.css 中的设计变量（优先使用变量而非硬编码值）

### Step 3: 生成代码骨架
根据技术栈生成:
- **React**: JSX组件 + CSS Module/Styled Components
- **Vue**: SFC (.vue) 文件
- **HTML**: 语义化HTML + CSS类

生成内容包含:
- 组件结构（基于Penpot层级）
- Props接口（基于ui-spec C-{NNN} Props定义）
- 变体支持（default/hover/active/disabled/error）
- 样式（引用 tokens.css 变量）
- 预留交互钩子（onClick等，基于 ui-spec 交互描述）

## Penpot MCP 工具发现
具体 MCP 工具名称以平台 MCP 配置为准（Claude: `.mcp.json` 或 `.claude/settings.json`；Cursor: `.cursor/mcp.json`；OpenCode: `opencode.json`），运行时通过可用工具列表自动发现。典型操作包括: 读取组件结构/样式/SVG。若工具列表中无 Penpot 相关工具，先运行 `cataforge penpot ensure` 尝试启动服务（若 Penpot 尚未部署则改运行 `cataforge penpot deploy`），仍不可用则返回 blocked。

## 效率策略
- 优先使用 tokens.css 变量，确保全局一致性
- 仅生成骨架和样式，业务逻辑由 TDD GREEN 阶段补充
- 组件代码遵循 arch#§7 开发约定
