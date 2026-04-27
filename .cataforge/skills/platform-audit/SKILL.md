---
name: platform-audit
description: "平台能力审计 — 检索 AI IDE 最新文档，与 CataForge 平台配置进行差异分析，输出更新方案并执行修复。适用于定期对齐 Claude Code / Cursor / Codex / OpenCode 等平台的 tool / hook / agent / dispatch / sandbox / CLI / plugin / 扩展能力 / agent配置 / 平台特性 / 权限模型 / 模型路由 能力变化，确保 profile.yaml、adapter 源码、hook bridge、conformance 检查、测试用例保持最新。当用户提到平台升级、能力变化、profile 过期、跨平台兼容性检查、新增平台接入时，务必使用此 skill。"
argument-hint: "[平台ID列表(逗号分隔) | all] [--scope tools,hooks,dispatch,agent,features,permissions,models,mcp]"
suggested-tools: Read, Edit, Write, Glob, Grep, Bash, WebSearch, WebFetch, Agent
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 平台能力审计 (platform-audit)

## 能力边界
- 能做: 检索各 AI IDE 最新能力文档、与现有 profile.yaml 差异分析、更新配置/源码/测试、运行合规检查
- 不做: 新增全新平台 adapter（需先在 `src/cataforge/platform/` 创建 adapter 类）、修改核心调度逻辑

## 设计原理

CataForge 通过多层抽象覆盖 AI IDE 的能力差异:

1. **核心能力 ID** (`CAPABILITY_IDS`) — 10 个必需的工具级映射（file_read, shell_exec, agent_dispatch 等）
2. **扩展能力 ID** (`EXTENDED_CAPABILITY_IDS`) — 部分平台独有的工具（notebook_edit, browser_preview, image_input, code_review）
3. **Agent 配置** (`AGENT_FRONTMATTER_FIELDS`) — 17 个 agent 定义 frontmatter 字段的跨平台超集
4. **平台特性** (`PLATFORM_FEATURES`) — 17 个 boolean 功能标志（cloud_agents, agent_teams, scheduled_tasks 等）
5. **权限模型** (`PermissionMode`) — 8 种审批模式的跨平台枚举
6. **模型路由** — 可用模型列表和 per-agent 模型选择支持
7. **Hook 事件** — 5 个标准事件 + 降级策略

每个平台通过 `profile.yaml` 声明它如何映射这些抽象。平台版本快速迭代（Cursor v3.x、Codex 2026.04、Claude Code 2.1、OpenCode 1.3），工具名称/hook 事件/agent 格式/功能特性随时可能变化。本 skill 将"检索 → 对比 → 更新 → 验证"的完整审计流程标准化，防止配置漂移。

## 输入规范
调用方提供:
- **审计范围**: 平台 ID 列表（默认 all = claude-code, cursor, codex, opencode）
- **关注维度**: tools / hooks / dispatch / agent / features / permissions / models / mcp（默认全部）
- **触发原因**（可选）: 如"Cursor 刚发布 v3.2"或"Codex 新增了沙箱模式"

## 输出规范
- 差异分析报告（结构化 Markdown）
- 更新后的 `profile.yaml` 文件
- 必要时更新的源码文件（adapter / bridge / types / conformance）
- 更新后的测试文件
- 合规检查（含扩展合规）+ 测试套件通过确认

---

## 操作指令

| 模式 | 适用场景 | 详见 |
|------|---------|------|
| **full** | 定期对齐（建议每月一次）或已知某平台有重大版本更新 | 指令 1 |
| **quick-check** | 只想知道当前配置是否过期，不执行修改 | 指令 2 |
| **deep `<platform_id>`** | 某平台刚发布重大更新，需深度审计 | 指令 3 |
| **evaluate `<platform_name>`** | 评估新 AI IDE 是否可接入 | `references/evaluate-new-platform.md` |

---

### 指令1: 完整审计 (full)

#### Phase 1: 文档检索与情报收集

> 此阶段的目标是建立每个平台的**最新能力快照**。不要依赖训练数据——平台更新非常频繁，profile.yaml 可能已经过期数月。

**Step 1: 读取当前配置基线**

并行读取所有目标平台的 `profile.yaml` (`.cataforge/platforms/<platform_id>/profile.yaml`)，提取并记录每个平台当前的:

- `version_tested` — 上次审计的版本号
- `tool_map` / `extended_capabilities` — 工具映射
- `agent_config.supported_fields` / `memory_scopes` / `isolation_modes` — agent 配置
- `features` — 17 个平台特性 flag
- `permissions.modes` — 支持的审批模式
- `model_routing` — 模型路由配置
- `hooks.event_map` / `tool_overrides` / `degradation` — hook 配置
- `agent_definition` — agent 格式和扫描目录
- `dispatch` — 调度方式和参数

**Step 2: 检索最新平台文档**

对每个目标平台，使用 WebSearch + WebFetch 获取**最新官方文档**。搜索策略（按优先级）:

1. 先尝试 ctx7 CLI（如果可用）:
   ```bash
   npx ctx7@latest library "<platform>" "tools hooks agent SDK"
   npx ctx7@latest docs "<libraryId>" "tool names hook events agent format"
   ```

2. 若 ctx7 不可用或结果不足，使用 WebSearch — 搜索词模板见 `references/platform-sources.md`，每个平台至少覆盖: 官方文档站、GitHub repo（README / CHANGELOG）、SDK reference

3. WebFetch 关键文档页面，提取: 工具/tool 列表、hook/lifecycle 事件、agent 定义格式、agent 高级特性（memory, isolation, model, effort, skills, mcpServers）、平台特性、权限/审批模式、可用模型、CLI 命令变化、沙箱模式、插件/extension 机制、MCP 配置格式、上下文窗口和模型版本

> 检索要点: 关注**工具名称的精确拼写**（大小写敏感）、**新增/移除/重命名的事件**、**配置文件路径变化**、**新增的 agent frontmatter 字段**、**新增的平台特性**。

**Step 3: 整理平台能力快照**

为每个平台填写 `references/snapshot-template.md` 的快照模板（**不写文件，保持在上下文中**），作为 Phase 2 差异对比的输入。

#### Phase 2: 差异分析

**Step 4: 逐维度对比**

对比 Phase 1 的快照与当前 profile.yaml，按以下维度逐一检查:

| 维度 | 对比项 | 影响级别判定 |
|------|--------|-------------|
| **tool_map** | 工具名称变化（重命名/新增/移除） | CRITICAL: 已有映射名称变更; MAJOR: 新增工具可映射; MINOR: null→仍然 null |
| **extended_capabilities** | 扩展能力变化 | MAJOR: null→有值（平台新增支持）; MINOR: 仍 null |
| **agent_config.supported_fields** | 支持字段变化 | MAJOR: 新增可支持字段; MINOR: 已声明字段不变 |
| **agent_config.memory_scopes** | memory scope 变化 | MAJOR: 新增 scope; MINOR: 不变 |
| **features** | 特性 flag 变化 | MAJOR: false→true（平台新增特性）; MINOR: 不变或 true→false |
| **permissions.modes** | 审批模式变化 | MAJOR: 新增模式; MINOR: 不变 |
| **model_routing** | 模型列表变化 | MAJOR: 新增模型; MINOR: 不变 |
| **hooks.event_map** | 事件名称/新增事件 | CRITICAL: 已有事件名变更; MAJOR: 新增可用事件 |
| **hooks.tool_overrides** | matcher 名称变化 | CRITICAL: override 名称与平台不符 |
| **hooks.degradation** | 降级状态可升级 | MAJOR: degraded→native 可升级; MINOR: 仍 degraded |
| **agent_definition** | 格式/路径变化 | CRITICAL: 格式不兼容; MAJOR: 路径变更 |
| **dispatch** | 调度方式/参数变化 | CRITICAL: 参数签名变更 |
| **version_tested** | 版本号过期 | INFO: 需要更新 |

**Step 5: 影响范围评估**

对每个差异项，评估波及的文件:

- `profile.yaml` — 几乎所有差异都需要更新
- `src/cataforge/core/types.py` — CAPABILITY_IDS / OPTIONAL / EXTENDED / AGENT_FRONTMATTER_FIELDS / PLATFORM_FEATURES / PermissionMode
- `src/cataforge/platform/<id>.py` — adapter 代码（tool_overrides / deploy_agents / inject_mcp_config）
- `src/cataforge/platform/base.py` — 基类属性（仅当新增通用属性时）
- `src/cataforge/hook/bridge.py` — hook 生成逻辑
- `src/cataforge/platform/conformance.py` — 合规检查逻辑
- `.cataforge/platforms/<id>/overrides/dispatch-prompt.md` — 调度提示模板
- `.cataforge/platforms/_schema.yaml` — profile 字段定义
- `tests/test_platform.py` / `test_hook_bridge.py` / `test_translator.py` / `test_conformance.py` / `test_deployer_refactor.py`

**Step 6: 输出差异报告**

按 `references/report-templates.md` 中的模板输出（直接展示给用户，不写文件）。

#### Phase 3: 执行更新

> 更新顺序很重要: profile.yaml 优先（它是所有其他文件的数据源），然后是 types.py，再是源码，最后是测试。

**Step 7: 更新 profile.yaml**

对每个需要更新的平台，按 Phase 2 的差异项更新对应字段（version_tested / tool_map / extended_capabilities / agent_config / features / permissions / model_routing / hooks / agent_definition / dispatch）。

**Step 8: 更新 types.py**

仅当需要新增跨平台抽象时:
- 新增 `EXTENDED_CAPABILITY_IDS` 条目 — 当新工具出现在 2+ 平台上
- 新增 `AGENT_FRONTMATTER_FIELDS` 条目 — 当新字段出现在 2+ 平台上
- 新增 `PLATFORM_FEATURES` 条目 — 当新特性出现在 2+ 平台上
- 新增 `PermissionMode` 枚举值 — 当新审批模式出现
- 调整 `OPTIONAL_CAPABILITY_IDS` — 当可选能力变为必需或反之

**Step 9: 更新源码**

仅当差异影响到源码逻辑时才修改。常见场景:

- **新增 hook_tool_overrides**: 在 `base.py` 已有通用 property，只需在 profile.yaml 配置
- **_md_to_toml() 变更**: 当 Codex agent 格式变化时修改 `codex.py`
- **新增 Capability ID**: 同时更新 `types.py` 和所有 `profile.yaml`
- **conformance 逻辑**: 当检查逻辑需要适配新维度时更新 `conformance.py`
- **bridge.py**: 当 hook 生成逻辑需要适配新事件类型时
- **deployer.py**: 当部署流程需要适配新的目标路径或配置格式时
- **base.py**: 仅当新增的 profile section 需要专用 accessor 方法时

> 原则: 优先用数据驱动（profile.yaml 新增 key）而非代码驱动（新增 adapter 方法）。profile.yaml 的 features / extended_capabilities / agent_config 设计允许新增 key 而无需修改 adapter 代码。

**Step 10: 更新 dispatch-prompt.md 模板**

检查 `.cataforge/platforms/<id>/overrides/dispatch-prompt.md`:
- `<!-- OVERRIDE:tool_usage -->` 中的工具名称是否与最新 tool_map 一致
- `<!-- OVERRIDE:context_limits -->` 中的上下文窗口/模型信息是否最新
- `<!-- OVERRIDE:dispatch_syntax -->` 中的调度参数是否正确

**Step 11: 更新测试**

对每个受影响的测试文件:
1. 更新 fixture 中的 profile 数据
2. 更新断言中的预期值（工具名称 / 事件名称 / 特性 flag）
3. 如有新增能力或降级状态变化，添加对应的测试用例
4. 保持现有测试的覆盖范围不缩减

#### Phase 4: 验证

**Step 12: 运行 conformance 检查**

核心 + 扩展合规:
```bash
python -c "from cataforge.platform.conformance import check_all_conformance; print('\n'.join(check_all_conformance()))"
python -c "from cataforge.platform.conformance import check_all_extended_conformance; print('\n'.join(check_all_extended_conformance()))"
```

确认所有平台通过核心合规（FAIL=0，WARN 仅针对已知缺失的可选能力）。扩展合规的 INFO 表示该平台不支持的扩展能力/特性，属于预期行为。

**Step 13: 运行完整测试套件**

```bash
python -m pytest tests/ -v
```

所有测试必须通过。如有失败: 分析（通常是 fixture 数据未同步更新）→ 修复 → 重跑。特别注意 `test_deployer_refactor.py` — 它使用内联 profile，不受 profile.yaml 变更影响，但 deployer 代码变更可能影响它。

**Step 14: 运行 linter**

```bash
python -m ruff check src/ tests/
```

确保修改的文件无 lint 错误。预先存在的非相关文件的 lint 错误无需修复。

**Step 15: 输出审计总结**

按 `references/report-templates.md` 中的"审计完成总结"模板输出。

---

### 指令2: 快速检查 (quick-check)

适用于: 只想知道当前配置是否过期，不执行修改。

1. 读取所有目标平台的 `profile.yaml`，记录 `version_tested`
2. WebSearch 每个平台的最新版本号
3. 对比版本号，标记过期平台
4. 对过期平台执行 Phase 2 的差异分析（Step 4-6）
5. 运行核心 + 扩展合规检查
6. 输出差异报告 + 合规状态，**不执行修改**

---

### 指令3: 单平台深度审计 (deep `<platform_id>`)

适用于: 某个平台刚发布重大更新，需要深度审计该平台。

执行完整审计流程（Phase 1-4），但仅针对指定平台。额外步骤:

**附加: 交叉验证**
1. 检查该平台的 `overrides/` 目录下所有文件是否需要更新
2. 检查 `hooks.yaml` 中所有 hook 脚本在该平台的降级状态是否正确
3. 检查该平台的 `inject_mcp_config()` 实现是否与最新 MCP 配置格式兼容
4. 如果该平台有 `tool_overrides`，验证 override 的工具名称在最新版中仍然有效
5. 验证 `agent_config.supported_fields` 是否完整覆盖平台最新的 agent frontmatter
6. 验证 `features` 中的 flag 是否反映平台最新发布的功能
7. 验证 `permissions.modes` 是否覆盖平台所有审批模式
8. 验证 `model_routing` 中的模型列表是否最新

---

### 指令4: 新平台接入评估 (evaluate `<platform_name>`)

完整流程见 `references/evaluate-new-platform.md`。**不修改仓库内任何文件**，输出可行性报告供决策。

---

## 关键检查维度详解

审计需要覆盖的维度见 `references/audit-checklist.md`。以下是最容易出问题的点:

### tool_map 映射陷阱
- **名称大小写**: Claude Code 用 `Bash`，Codex 用 `shell`，OpenCode 用 `bash` — 大小写敏感
- **合并工具**: Cursor v3 将 `file_edit` 和 `file_write` 合并为同一个 `Write` 工具
- **null 语义**: `null` 表示平台不提供该能力，不是"未知" — 需确认是真的不支持还是名称未查到
- **hook matcher vs tool_map**: 有些平台的 hook 事件使用不同于 tool_map 的工具名称（如 Codex tool_map 用 `shell` 但 hook 用 `Bash`），此时需配置 `hooks.tool_overrides`

### extended_capabilities 扩展原则
- 新增扩展能力 key 时只需: (1) 在 `types.py` 的 `EXTENDED_CAPABILITY_IDS` 添加 (2) 在各 `profile.yaml` 的 `extended_capabilities` 添加
- 无需修改 adapter 代码 — `get_extended_tool_map()` 自动读取 profile
- 当某个扩展能力被 3+ 平台支持时，考虑提升为核心能力

### agent_config 字段管理
- `supported_fields` 列出该平台的 agent frontmatter 支持哪些字段
- 新增跨平台字段时: (1) 添加到 `types.py` 的 `AGENT_FRONTMATTER_FIELDS` (2) 在支持该字段的平台 profile 的 `supported_fields` 中添加
- 平台特有字段（如 Codex 的 `sandbox_mode`）也列在该平台的 `supported_fields` 中

### features 特性管理
- `features` 中的 key 可自由扩展，无需修改 adapter 代码
- 新增 key 时: (1) 添加到 `types.py` 的 `PLATFORM_FEATURES` (2) 在各 `profile.yaml` 添加
- 特性 flag 为 `false` 不等于"不知道"，它表示"审计时确认不支持"

### hooks.degradation 判定标准
- **native**: 平台原生支持该 hook 的事件类型 + 对应的 matcher/工具
- **degraded**: 平台不支持某环节（如无 Notification 事件、无 agent matcher），需降级为规则注入/prompt 指令/跳过

### 版本号约定
- `version_tested` 记录的是 **审计时的平台版本**，不是 CataForge 版本
- 格式跟随各平台自己的版本号格式（如 Cursor 用语义化版本 "3.1"，Codex 用日期版本 "2026.04"）

## 效率策略
- **并行检索**: 对多个平台的文档检索应尽量并行（使用 Agent 工具分派子任务）
- **增量更新**: 如果 `version_tested` 与最新版本相同，跳过该平台（除非用户强制审计）
- **profile 优先**: 所有变更从 profile.yaml 开始，它是整个系统的 single source of truth
- **数据驱动优先**: 新增能力/特性优先在 profile.yaml 添加 key，而非修改 adapter 代码
- **测试驱动**: 先更新测试中的预期值，再修改源码，确保修改方向正确
- **最小变更**: 不重构无关代码，只更新审计发现的差异项
