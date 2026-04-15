# 平台能力矩阵

本文档汇总四个目标平台的能力差异，供 workflow-framework-generator 在架构规划阶段查阅。

## 核心工具映射

| 能力标识符 | Claude Code | Cursor | CodeX | OpenCode |
|-----------|-------------|--------|-------|----------|
| file_read | Read | Read | shell (cat) | read |
| file_write | Write | Write | apply_patch | write |
| file_edit | Edit | Write | apply_patch | edit |
| file_glob | Glob | Glob | shell (find) | glob |
| file_grep | Grep | Grep | shell (grep) | grep |
| shell_exec | Bash | Shell | shell | bash |
| web_search | WebSearch | WebSearch | web_search | websearch |
| web_fetch | WebFetch | **null** | shell (curl) | webfetch |
| user_question | AskUserQuestion | **null** | **null** | question |
| agent_dispatch | Agent | Task | spawn_agent | task |

**null** 表示该平台无对应工具，需要降级处理。

## 代理能力对比

| 特性 | Claude Code | Cursor | CodeX | OpenCode |
|------|-------------|--------|-------|----------|
| 多代理调度 | Agent (同步) | Task (同步) | spawn_agent (异步) | task (同步) |
| 并行代理 | 最多10个 | 最多8个 | cloud并行 | 不支持 |
| 后台代理 | 支持 | 支持 | 支持 | 不支持 |
| 代理内存 | user/project/local | 不支持 | 不支持 | 不支持 |
| 工作树隔离 | worktree | worktree | 不支持 | 不支持 |
| 代理配置格式 | YAML frontmatter | YAML frontmatter | TOML | YAML frontmatter |

## Hook 支持

| 特性 | Claude Code | Cursor | CodeX | OpenCode |
|------|-------------|--------|-------|----------|
| 配置格式 | JSON (.claude/settings.json) | JSON (.cursor/hooks.json) | JSON (.codex/hooks.json) | JS/TS 插件 |
| PreToolUse | 原生 | 原生 | 原生 (仅Bash) | 需插件适配 |
| PostToolUse | 原生 | 原生 | 原生 (仅Bash) | 需插件适配 |
| Stop | 原生 | 原生 | 原生 | session.idle |
| SessionStart | 原生 | 原生 | 原生 | session.created |

## 平台独有特性

### Claude Code
- Plan mode (EnterPlanMode / ExitPlanMode)
- Agent memory (user/project/local scopes)
- Chapter marking and context management
- Plugin marketplace

### Cursor
- Cloud agents (isolated VMs)
- Computer use (click, screenshot, record)
- Autonomy slider (Tab → edit → full agent)
- BugBot code review service

### CodeX
- Best-of-N cloud parallel (--attempts)
- Realtime voice (WebRTC v2)
- Session resume (/resume)
- Multi-root workspace (--add-dir)
- Native computer use

### OpenCode
- 75+ model providers via Models.dev
- Git-backed session review
- CI/CD integration (github install/run)
- JS/TS plugin system

## 降级策略矩阵

当目标平台缺少某能力时，按以下策略降级：

| 缺失能力 | 降级策略 | 适用平台 |
|---------|---------|---------|
| web_fetch | shell_exec + curl 命令 | Cursor |
| user_question | 在 Agent 指令中嵌入"如信息不足则在 output 中列出待确认项" | Cursor, CodeX |
| parallel_agents | 所有代理按顺序串行执行 | OpenCode |
| background_agents | 等待代理完成后再继续 | OpenCode |
| agent_memory | 通过文件系统持久化关键上下文 | Cursor, CodeX, OpenCode |
| worktree_isolation | 在同一工作目录执行，注意文件冲突 | CodeX, OpenCode |
| plan_mode | 在 Agent 指令中添加"先列出计划再执行"的约束 | Cursor, CodeX |
| hooks (原生) | 将逻辑嵌入 Agent 指令的 Anti-Patterns 章节 | OpenCode |

## 代理配置字段支持

| 字段 | Claude Code | Cursor | CodeX | OpenCode |
|------|-------------|--------|-------|----------|
| name | Y | Y | Y | Y |
| description | Y | Y | Y | Y |
| tools | Y | Y | - | Y |
| disallowedTools | Y | Y | - | - |
| model | Y | Y | Y | Y |
| maxTurns | Y | Y | - | - |
| skills | Y | - | - | - |
| mcpServers | Y | Y | - | - |
| hooks | Y | Y | - | - |
| memory | Y | - | - | - |
| background | Y | Y | - | - |
| isolation | Y | Y | - | - |
| permissionMode | Y | - | - | - |
| sandbox_mode | - | - | Y | - |

字段不支持时的处理：忽略该字段，相关逻辑嵌入 Agent 指令正文。
