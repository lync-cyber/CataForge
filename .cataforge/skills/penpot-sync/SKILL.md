---
name: penpot-sync
description: "Penpot 设计 Token 双向同步 — Penpot 设计文件与代码 / 文档间的颜色 / 字号 / 间距 / 圆角等 Token 同步。当 ui-spec 与 Penpot 设计的 token 不一致 / 需在两端互导时使用此 skill。本 skill 仅处理 Token 维度；组件代码生成由 penpot-implement 负责，设计 ↔ 代码一致性验证由 penpot-review 负责。"
argument-hint: "<sync-direction: penpot-to-code|code-to-penpot|bidirectional>"
suggested-tools: file_read, file_write, file_edit, file_glob, file_grep
depends: [context]
disable-model-invocation: false
user-invocable: true
---

# 设计Token双向同步 (penpot-sync)
## 能力边界
- 能做: 从Penpot读取设计Token、将Token写入CSS变量文件、从ui-spec同步Token到Penpot、Token一致性检查
- 不做: 组件设计、页面布局、代码实现、以 Penpot 为权威源反写 ui-spec（Step 4 bidirectional 仅以 ui-spec 为权威源，从 Penpot 读取 Token 仅用于比对）

## 前置条件
- {INSTRUCTION_FILE} `设计工具` 字段为 `penpot`
- Penpot MCP Server 已配置并可用（Claude: `.mcp.json` / `.claude/settings.json`；Cursor: `.cursor/mcp.json`；OpenCode: `opencode.json`）
- 若 Penpot MCP 不可用，返回 blocked 并提示用户检查配置

## 输入规范
- ui-spec#§1 设计系统Token表（色彩/排版/间距）
- Penpot 项目 ID（从 {INSTRUCTION_FILE} 或用户输入获取）

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
- `bidirectional`(默认): 以 ui-spec 为唯一权威源，顺序执行两次受控单向写出（→ Penpot、→ tokens.css），不读回 Penpot 端改动反写 ui-spec，故无覆盖循环

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
具体 MCP 工具名称以平台 MCP 配置为准（Claude: `.mcp.json` 或 `.claude/settings.json`；Cursor: `.cursor/mcp.json`；OpenCode: `opencode.json`），运行时通过可用工具列表自动发现。典型操作包括: 读取项目信息、读取组件结构/样式、写入设计 Token。若工具列表中无 Penpot 相关工具，先运行 `cataforge penpot ensure` 尝试启动服务（若 Penpot 尚未部署则改运行 `cataforge penpot deploy`），仍不可用则返回 blocked。

## Anti-Patterns
- 禁止: 全量覆盖远端 Token —— 必须局部增量同步，保留 Penpot 端的手动微调；全量覆盖会丢失设计师未提交回 ui-spec 的中间状态
- 禁止: 同步时跳过 ui-spec 比对 —— ui-spec.md 中的 Token 命名是契约源；不比对会让 Penpot 命名漂移持久化
- 禁止: 在 Penpot 未启动时静默返回 success —— `cataforge penpot ensure` 失败时必须返回 blocked，否则下游 implementer 在空 Token 上施工
- 避免: 无权威源的双向自动回写 —— Penpot 端改动反写 ui-spec、ui-spec 又写回 Penpot 会产生覆盖循环；默认 `bidirectional` 仅以 ui-spec 为权威源做两次单向写出，不反向读回

## 效率策略
- 仅同步有差异的Token，不全量覆盖
- Token命名遵循 ui-spec 中的命名规范
