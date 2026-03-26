---
name: penpot-sync
description: "设计Token双向同步 — Penpot设计文件与代码/文档间的Token同步。"
argument-hint: "<sync-direction: penpot-to-code|code-to-penpot|bidirectional>"
suggested-tools: Read, Write, Edit, Glob, Grep
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 设计Token双向同步 (penpot-sync)
## 能力边界
- 能做: 从Penpot读取设计Token、将Token写入CSS变量文件、从ui-spec同步Token到Penpot、Token一致性检查
- 不做: 组件设计、页面布局、代码实现

## 前置条件
- CLAUDE.md `设计工具` 字段为 `penpot`
- Penpot MCP Server 已配置并可用（见 .claude/settings.json mcpServers.penpot）
- 若 Penpot MCP 不可用，返回 blocked 并提示用户检查配置

## 输入规范
- ui-spec#§1 设计系统Token表（色彩/排版/间距）
- Penpot 项目 ID（从 CLAUDE.md 或用户输入获取）

## 输出规范
- `src/styles/tokens.css` — CSS变量文件（W3C Design Tokens 格式）
- Token同步报告（差异列表 + 冲突解决记录）

## 执行流程

### Step 1: 检测 Penpot MCP 可用性
- 尝试通过 Penpot MCP 工具读取项目信息
- 不可用 → 返回 blocked，提示: "Penpot MCP Server 未连接，请确认 Penpot 和 MCP Plugin 已启动"

### Step 2: 读取现有 Token
- 从 ui-spec#§1 读取文档中定义的设计系统Token
- 从 Penpot MCP 读取项目中的设计Token（如已存在）
- 从 `src/styles/tokens.css` 读取代码中的Token（如已存在）

### Step 3: 三方对齐
- 对比三个来源的Token差异
- 冲突优先级: ui-spec（权威源）> Penpot > tokens.css
- 生成差异报告:
  - 新增: 仅在一方存在的Token
  - 冲突: 同名Token不同值
  - 一致: 三方相同

### Step 4: 执行同步
根据 sync-direction 参数:
- `penpot-to-code`: Penpot Token → tokens.css
- `code-to-penpot`: ui-spec Token → Penpot（通过 MCP 写入）
- `bidirectional`(默认): ui-spec 为权威源，同时更新 Penpot 和 tokens.css

### Step 5: 产出 tokens.css
格式示例:
```css
:root {
  /* Color Tokens */
  --color-primary: #3B82F6;
  --color-secondary: #10B981;
  /* Typography Tokens */
  --font-family-base: 'Inter', sans-serif;
  --font-size-base: 16px;
  /* Spacing Tokens */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
}
```

## Penpot MCP 工具发现
具体 MCP 工具名称以 .claude/settings.json 中 `mcpServers.penpot` 配置为准，运行时通过可用工具列表自动发现。典型操作包括: 读取项目信息、读取组件结构/样式、写入设计 Token。若工具列表中无 Penpot 相关工具，返回 blocked。

## 效率策略
- 仅同步有差异的Token，不全量覆盖
- Token命名遵循 ui-spec 中的命名规范
