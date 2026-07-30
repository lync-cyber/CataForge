# 平台能力矩阵

本文档供 workflow-framework-generator 在架构规划阶段查阅。生成的 profile 必须使用类型化 `CapabilityBinding`，不得输出旧 `string|null` 语法。

## 核心工具映射

| capability | Claude Code | Cursor | Codex | OpenCode |
|---|---|---|---|---|
| file_read | Read · native | Read · native | shell · replacement | read · native |
| file_write | Write · native | Write · native | apply_patch · native | write · native |
| file_edit | Edit · native | Write · native | apply_patch · native | edit · native |
| file_glob | Glob · native | Glob · native | shell · replacement | glob · native |
| file_grep | Grep · native | Grep · native | shell · replacement | grep · native |
| shell_exec | Bash · native | Shell · native | shell · native | bash · native |
| web_search | WebSearch · native | WebSearch · native | web_search · native | websearch · native |
| web_fetch | WebFetch · native | unsupported | shell · replacement | webfetch · native |
| user_question | AskUserQuestion · native | unsupported | request_user_input · conditional native | question · native |
| agent_dispatch | Agent · native | Task · native | spawn_agent · native | task · native |

Codex `request_user_input` 仅 root thread 可用：Plan 模式原生；Default 模式要求 `default_mode_request_user_input` feature；subagent 不可用。生成器不得自动开启该 feature。

## Hook 支持

| 特性 | Claude Code | Cursor | Codex | OpenCode |
|---|---|---|---|---|
| 配置格式 | JSON | JSON | JSON | JS/TS plugin |
| PreToolUse | 原生 | 原生 | 原生 | plugin |
| PostToolUse | 原生 | 原生 | **原生，支持 request_user_input matcher** | plugin |
| Stop | 原生 | 原生 | 原生 | session.idle |
| SessionStart | 原生 | 原生 | 原生 | session.created |

Hook 必须用 `hooks.policies.<script>` 声明 `native|hybrid|degraded|unsupported`。模型工具名与 hook matcher 不同时，写入 capability binding 的 `hook_matchers`。

## Agent 权限

| 平台 | tool_policy | 生成规则 |
|---|---|---|
| Claude Code | allow_deny | 编译 allow / deny |
| Cursor | allow_deny | 编译 allow / deny |
| Codex | inherit_only | 不生成 per-agent 工具字段；全写能力被禁止时可证明为 read-only |
| OpenCode | allow_only | 只生成 allow；deny 标为 unenforced |

同一平台工具对应多个 capability 时先建立等价类；等价类内 allow/deny 混合是配置错误，禁止静默扩大权限。

## 生成约束

- `kind` 只允许 `native`、`replacement`、`unsupported`。
- `unsupported` 必须使用 `tool: null`。
- 条件能力使用 `availability.any_of[]`，条件只包含 thread scope、collaboration mode 与 required feature。
- fallback 必须声明 `coverage: equivalent|partial|none` 与 `reason`。
- 不使用 hook、command rule 或虚构字段模拟平台不支持的 per-agent 权限。
