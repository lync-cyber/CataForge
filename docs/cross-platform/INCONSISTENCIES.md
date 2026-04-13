# 方案与代码不一致记录

> 基于 foamy-tumbling-curry.md（v2 方案）与代码库实态（v0.9.13）的对比分析。
> 标注 CONFIRMED = 方案与代码一致（已确认）；INCONSISTENT = 存在偏差需修正。
> 注意: Phase 0 目录重构后，所有框架文件路径从 `.claude/` 迁移至 `.cataforge/`。

---

## CONFIRMED 项（方案与代码一致）

### C-1: Agent 和 Skill 数量
- 方案声称: "13 Agent、22 Skill"
- 实际代码: 13 个 `AGENT.md` + 22 个 `SKILL.md`
- **一致**

### C-2: agent-dispatch/SKILL.md:74 引用
- 方案引用: `agent-dispatch/SKILL.md:74` 明确声明"当前版本仅支持 claude-code runtime"
- 实际代码 L74-75: `当前版本仅支持 claude-code runtime。其他运行时（Cursor、Codex 等）为规划中功能。`
- **一致**

### C-3: agent-dispatch/SKILL.md:38-44 引用
- 方案 §二 H-2: `agent-dispatch/SKILL.md:38-44` 为调度工具 API 差异位置
- 实际代码 L38-44: `## claude-code 实现 (默认)` 段落
- **一致**

### C-4: tdd-engine/SKILL.md:22-26 引用
- 方案引用: 架构图中 `通过Agent tool启动` 部分
- 实际代码 L20-26: 正是 orchestrator → RED/GREEN/REFACTOR 的架构图
- **一致**（行号微偏 20 vs 22，因 frontmatter 计数差异）

### C-5: settings.json:56-138 引用
- 方案 §二 H-4: `.claude/settings.json:56-138` 为 hooks 段落
- 实际代码: hooks 段落位于 L56-138
- **一致**

---

## INCONSISTENT 项（需修正）

### I-1: 方案遗漏 ORCHESTRATOR-PROTOCOLS.md 影响分析
- **严重度**: HIGH
- **问题**: v2 方案没有提及 `ORCHESTRATOR-PROTOCOLS.md`（411 行）的修改需求
- **实际影响**:
  - Bootstrap Step 6 的 `setup.py --apply-permissions` 生成 Claude Code 专用 `Bash(...)` 权限格式
  - 跨平台后其他平台需要不同的权限格式（Codex: `sandbox_mode`，OpenCode: `permission` 对象）
  - 协议中需增加平台选择步骤
- **修正**: Phase 4 Step 4.2 已覆盖此修改
- **状态**: 已在执行计划中处理

### I-2: 方案遗漏 setup.py --apply-permissions 跨平台影响
- **严重度**: MEDIUM
- **问题**: `setup.py --apply-permissions` 生成 Claude Code 专用的 `Bash(...)` 权限条目
- **实际影响**: Cursor/Codex/OpenCode 各有不同权限模型
- **修正**: Phase 4 Step 4.2 中 setup.py 添加 `--platform` 参数；各适配器可提供 `generate_permissions()` 方法
- **状态**: 已在执行计划中处理

### I-3: Cursor tool_map 映射错误
- **严重度**: HIGH
- **问题**: v2 方案 §三.5 的 `tool_map.yaml` Cursor 段落包含多个错误
- **错误映射**:

| 能力 | 方案中 Cursor 映射 | 实际 Cursor API |
|------|-------------------|----------------|
| `file_edit` | `Write` | `StrReplace`（独立工具） |
| `file_glob` | `Read` | `Glob`（独立工具） |
| `file_grep` | `Read` | `Grep`（独立工具） |
| `web_search` | `null` | `WebSearch`（存在） |
| `web_fetch` | `null` | `WebFetch`（存在） |

- **修正**: Phase 1 Step 1.1 的 `tool_map.yaml` 已使用纠正后的映射
- **状态**: 已在执行计划中处理

### I-4: 方案遗漏 _hook_base.py 共享模块分析
- **严重度**: MEDIUM
- **问题**: 所有 8 个 Hook 脚本依赖 `_hook_base.py` 的 `read_hook_input()` 和 `hook_main()`，但方案未分析此文件是否需要跨平台适配
- **实际影响**: 不同平台的 Hook stdin JSON 格式可能有差异（字段名、数据结构）
- **当前代码**: `_hook_base.py` L13-27 仅做 UTF-8 stdin 读取，无平台检测
- **修正**: Phase 3 Step 3.1 已设计统一解析层（含平台检测和能力匹配）
- **状态**: 已在执行计划中处理

### I-5: AGENT.md tools/disallowedTools 跨平台处理策略不完整
- **严重度**: MEDIUM
- **问题**: 方案 §二 M-1 提到"工具能力映射表"，但未明确 AGENT.md frontmatter 中的 `tools:` 和 `disallowedTools:` 值是保持 Claude Code 工具名还是改为能力标识符
- **决策**: 已确认使用能力标识符（决策 D-1）
- **实际影响**: 13 个 AGENT.md 全部需要修改 frontmatter
- **修正**: Phase 1 Step 1.6 已包含完整的 13 个 AGENT.md 变更清单
- **状态**: 已在执行计划中处理

### I-6: InstructionFileSync 对 Cursor 的评估过于简化
- **严重度**: LOW
- **问题**: 方案声称 Cursor 指令文件从 CLAUDE.md "提取静态规则生成"
- **实际 Cursor rules 系统**: 使用 MDC 格式（YAML frontmatter + Markdown），支持 `globs`、`description`、`alwaysApply` 等字段
- **影响**: 简单提取不足以覆盖 CataForge 的 always-applied workspace rules 行为
- **修正**: Phase 2 Step 2.2 的 `cursor_rules_gen.py` 已设计 MDC 格式输出（含 alwaysApply 字段）
- **状态**: 已在执行计划中处理

---

## 版本号语义澄清

| 位置 | 字段 | 当前值 | 语义 |
|------|------|--------|------|
| `pyproject.toml` | `[project].version` | `0.9.13` | CataForge 发行版本 |
| `framework.json` | `version` | `0.3.0` | 框架配置 schema 版本 |
| `framework.json` | `runtime_api_version`（Phase 1 新增） | `1.0` | 运行时接口 API 版本 |

三者独立演进，各有其语义。方案中的 `runtime_api_version: 1.0`（Phase 4）应作为**新字段**加入 `framework.json`，与现有 `version` 并存。

---

### I-7: 方案未考虑目录结构解耦
- **严重度**: HIGH
- **问题**: v2 方案将所有新建的 runtime 包放在 `.claude/runtime/`，但 `.claude/` 是 Claude Code 的平台约定目录，不应承载平台无关的框架核心逻辑
- **影响**: 框架 87 个文件（agents/skills/rules/schemas/scripts/hooks/integrations/framework.json）全部混合在 Claude Code 平台目录中
- **修正**: Phase 0 目录重构，建立 `.cataforge/` 为框架核心目录，`.claude/` 仅保留 `settings.json` + 同步链接
- **状态**: 已在 phase-0-directory-restructure.md 中完整规划

---

## 总结

| 分类 | 数量 |
|------|:----:|
| CONFIRMED（一致） | 5 |
| INCONSISTENT（需修正） | 7 |
| 已在执行计划中处理 | 7/7 |
| 仍待处理 | 0 |
