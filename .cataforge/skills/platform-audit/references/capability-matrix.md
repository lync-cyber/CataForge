# CataForge 能力矩阵参考

本文件记录 CataForge 定义的所有标准能力维度及其跨平台映射基线。审计时以此为起点，对比最新文档。

> 此文件为参考快照，不是实时数据。真实映射以各平台 `profile.yaml` 为准。

---

## 核心 Capability IDs (10)

CataForge 定义 10 个平台无关的核心能力标识符:

| # | Capability ID | 语义 | 必需/可选 |
|---|--------------|------|----------|
| 1 | `file_read` | 读取文件内容 | 必需 |
| 2 | `file_write` | 写入/创建文件 | 必需 |
| 3 | `file_edit` | 编辑已有文件（增量修改） | 必需 |
| 4 | `file_glob` | 按模式搜索文件名 | 必需 |
| 5 | `file_grep` | 按内容搜索文件 | 必需 |
| 6 | `shell_exec` | 执行 shell 命令 | 必需 |
| 7 | `web_search` | 网络搜索 | 必需 |
| 8 | `web_fetch` | 获取网页内容 | 可选 |
| 9 | `user_question` | 向用户提问 | 可选 |
| 10 | `agent_dispatch` | 派遣子 agent/task | 必需 |

### 可选能力说明
- `web_fetch`: 部分平台不提供独立的 web fetch 工具（如 Cursor）
- `user_question`: 异步平台（如 Codex）无法交互式提问；部分平台该工具尚不稳定

可选能力在 conformance 检查中报 INFO 而非 WARN。

代码位置: `src/cataforge/core/types.py` — `CAPABILITY_IDS`, `OPTIONAL_CAPABILITY_IDS`

---

## 扩展 Capability IDs (4)

部分平台独有的工具级能力。conformance 视为 INFO（仅报告）:

| # | Capability ID | 语义 | 典型平台 |
|---|--------------|------|---------|
| 1 | `notebook_edit` | Jupyter notebook 编辑 | Claude Code: NotebookEdit |
| 2 | `browser_preview` | 浏览器自动化/预览 | Claude Code: preview_* (MCP), Cursor: computer |
| 3 | `image_input` | 图片/截图输入 | Codex: -i flag, OpenCode: drag-drop, Claude Code: Read |
| 4 | `code_review` | 专用代码审查工具 | Codex: /review |

### 扩展原则
- 新增 key 只需修改 `types.py` 和各 `profile.yaml`，无需修改 adapter 代码
- 当 3+ 平台支持某扩展能力时，考虑提升为核心能力

代码位置: `src/cataforge/core/types.py` — `EXTENDED_CAPABILITY_IDS`

---

## Agent Frontmatter Fields (17)

Agent 定义支持的 frontmatter 字段超集:

| # | 字段 | 语义 | Claude Code | Cursor | Codex | OpenCode |
|---|------|------|------------|--------|-------|----------|
| 1 | `name` | 唯一标识符 | ✓ | ✓ | ✓ | ✓ |
| 2 | `description` | 何时委派 | ✓ | ✓ | ✓ | ✓ |
| 3 | `tools` | 允许的工具 | ✓ | ✓ | - | ✓ |
| 4 | `disallowedTools` | 禁止的工具 | ✓ | ✓ | - | - |
| 5 | `model` | 使用的模型 | ✓ | ✓ | ✓ | ✓ |
| 6 | `permissionMode` | 审批模式 | ✓ | - | - | - |
| 7 | `maxTurns` | 最大轮次 | ✓ | ✓ | - | - |
| 8 | `skills` | 注入的 skill | ✓ | - | - | - |
| 9 | `mcpServers` | MCP 服务器 | ✓ | ✓ | - | - |
| 10 | `hooks` | 生命周期 hook | ✓ | ✓ | - | - |
| 11 | `memory` | 持久化记忆 | ✓ | - | - | - |
| 12 | `background` | 后台运行 | ✓ | ✓ | - | - |
| 13 | `effort` | 推理努力级别 | ✓ | - | - | - |
| 14 | `isolation` | 隔离模式 | ✓ | - | - | - |
| 15 | `color` | 显示颜色 | ✓ | - | - | - |
| 16 | `initialPrompt` | 首条自动消息 | ✓ | - | - | - |
| 17 | `prompt` | 系统提示 (CLI) | ✓ | - | - | - |

> Codex 另有平台特有字段: `model_reasoning_effort`, `sandbox_mode`, `nickname_candidates`

代码位置: `src/cataforge/core/types.py` — `AGENT_FRONTMATTER_FIELDS`

---

## Platform Features (17)

平台级功能特性 boolean flags:

| # | Feature | 语义 | Claude Code | Cursor | Codex | OpenCode |
|---|---------|------|------------|--------|-------|----------|
| 1 | `cloud_agents` | 远程/云端 agent 执行 | - | ✓ | ✓ | - |
| 2 | `agent_teams` | 多 session agent 协作 | ✓* | - | - | - |
| 3 | `parallel_agents` | 并发 agent 执行 | ✓(10) | ✓(8) | ✓ | - |
| 4 | `scheduled_tasks` | 定时/事件触发 agent | ✓ | ✓ | - | - |
| 5 | `background_agents` | 后台 agent 执行 | ✓ | ✓ | ✓ | - |
| 6 | `plan_mode` | 只读规划模式 | ✓ | - | - | ✓ |
| 7 | `computer_use` | 原生 UI/浏览器自动化 | - | ✓ | ✓ | - |
| 8 | `realtime_voice` | 语音输入/输出 | - | - | ✓ | - |
| 9 | `multi_model` | 多模型选择 | ✓ | ✓ | ✓ | ✓ |
| 10 | `session_resume` | session 持久化恢复 | - | - | ✓ | ✓ |
| 11 | `worktree_isolation` | Git worktree 隔离 | ✓ | ✓ | - | - |
| 12 | `autonomy_slider` | 可配置自治级别 | - | ✓ | - | - |
| 13 | `ci_cd_integration` | 原生 CI/CD 集成 | - | - | - | ✓ |
| 14 | `multi_root` | 多项目工作区 | - | - | ✓ | - |
| 15 | `agent_memory` | Agent 级持久化记忆 | ✓ | - | - | - |
| 16 | `plugin_marketplace` | Plugin 发现和安装 | ✓ | ✓ | ✓ | ✓ |
| 17 | `context_management` | 上下文窗口管理 | ✓ | - | - | - |

> ✓* = experimental

代码位置: `src/cataforge/core/types.py` — `PLATFORM_FEATURES`

---

## Permission Modes (8)

跨平台审批模式枚举:

| # | Mode | 语义 | Claude Code | Cursor | Codex | OpenCode |
|---|------|------|------------|--------|-------|----------|
| 1 | `default` | 标准权限提示 | ✓ | ✓ | - | ✓ |
| 2 | `accept_edits` | 自动接受文件编辑 | ✓ | - | - | - |
| 3 | `auto` | 分类器自动审批 | ✓ | ✓ | ✓ | - |
| 4 | `dont_ask` | 自动拒绝提示 | ✓ | - | - | - |
| 5 | `bypass` | 跳过所有权限提示 | ✓ | - | - | - |
| 6 | `plan` | 只读探索 | ✓ | - | - | - |
| 7 | `read_only` | 顾问模式 | - | - | ✓ | - |
| 8 | `full_access` | 无限制 | - | - | ✓ | - |

代码位置: `src/cataforge/core/types.py` — `PermissionMode`

---

## Hook Events (5)

CataForge 定义 5 个标准 hook 事件:

| # | 标准事件 | 触发时机 | 用途 |
|---|---------|---------|------|
| 1 | `PreToolUse` | 工具调用前 | 安全守卫、参数校验、审批 |
| 2 | `PostToolUse` | 工具调用后 | lint/格式化、日志记录、结果校验 |
| 3 | `Stop` | 任务/会话结束 | 完成通知、清理 |
| 4 | `SessionStart` | 会话/对话开始 | 上下文注入、环境初始化 |
| 5 | `Notification` | 权限请求/系统通知 | 权限审批通知 |

### Hook 脚本清单

当前定义的 hook 脚本:

| 脚本名 | 事件 | matcher 能力 | 功能 |
|--------|------|-------------|------|
| `guard_dangerous` | PreToolUse | shell_exec | 阻止危险命令（rm -rf、drop table 等） |
| `log_agent_dispatch` | PreToolUse | agent_dispatch | 记录子 agent 派遣 |
| `validate_agent_result` | PostToolUse | agent_dispatch | 校验子 agent 返回结果 |
| `lint_format` | PostToolUse | file_edit | 编辑后自动 lint/格式化 |
| `detect_correction` | PreToolUse | user_question | 检测用户纠正意图 |
| `notify_done` | Stop | (无 matcher) | 任务完成通知 |
| `notify_permission` | Notification | (无 matcher) | 权限请求通知 |
| `session_context` | SessionStart | (无 matcher) | 注入会话上下文 |

---

## 跨平台映射基线

以下为各平台的典型映射（可能因版本更新而变化，审计时以最新文档为准）:

### Core Tool Names

| Capability | Claude Code | Cursor | Codex | OpenCode |
|-----------|-------------|--------|-------|----------|
| file_read | Read | Read | shell | read |
| file_write | Write | Write | apply_patch | write |
| file_edit | Edit | Write | apply_patch | edit |
| file_glob | Glob | Glob | shell | glob |
| file_grep | Grep | Grep | shell | grep |
| shell_exec | Bash | Shell | shell | bash |
| web_search | WebSearch | WebSearch | web_search | websearch |
| web_fetch | WebFetch | *null* | shell | webfetch |
| user_question | AskUserQuestion | *null* | *null* | question |
| agent_dispatch | Agent | Task | spawn_agent | task |

### Extended Capability Names

| Capability | Claude Code | Cursor | Codex | OpenCode |
|-----------|-------------|--------|-------|----------|
| notebook_edit | NotebookEdit | *null* | *null* | *null* |
| browser_preview | preview_start | computer | *null* | *null* |
| image_input | Read | *null* | image | image |
| code_review | *null* | *null* | review | *null* |

### Hook Event Names

| 标准事件 | Claude Code | Cursor | Codex | OpenCode |
|---------|-------------|--------|-------|----------|
| PreToolUse | PreToolUse | preToolUse | PreToolUse | tool.execute.before |
| PostToolUse | PostToolUse | postToolUse | PostToolUse | tool.execute.after |
| Stop | Stop | stop | Stop | session.idle |
| SessionStart | SessionStart | sessionStart | SessionStart | session.created |
| Notification | Notification | *null* | *null* | *null* |

### Hook Tool Overrides

仅当 hook matcher 名称与 tool_map 不同时需要:

| 平台 | Capability | tool_map 值 | hook override 值 | 原因 |
|------|-----------|-------------|-----------------|------|
| Codex | shell_exec | shell | Bash | Codex hook 事件内部使用 "Bash" 标识 |

### Hook Config

| 平台 | 格式 | 路径 |
|------|------|------|
| Claude Code | JSON | .claude/settings.json |
| Cursor | JSON | .cursor/hooks.json |
| Codex | JSON | .codex/hooks.json |
| OpenCode | plugin | .opencode/plugins/ (JS/TS) |

### Agent Format

| 平台 | 格式 | 扫描目录 | 需要部署 |
|------|------|---------|---------|
| Claude Code | yaml-frontmatter | .claude/agents | Yes |
| Cursor | yaml-frontmatter | .cursor/agents, .claude/agents | Yes |
| Codex | toml | .codex/agents | Yes |
| OpenCode | yaml-frontmatter | .opencode/agents, .claude/agents | Yes |

### Dispatch

| 平台 | 工具 | 异步 | 参数 |
|------|------|------|------|
| Claude Code | Agent | No | subagent_type, prompt, description |
| Cursor | Task | No | subagent_type, prompt, description, model |
| Codex | spawn_agent | Yes | agent, fork_context, prompt |
| OpenCode | task | No | subagent_type, description, prompt |

### Model Routing

| 平台 | 可用模型 | Per-agent |
|------|---------|----------|
| Claude Code | opus, sonnet, haiku | Yes |
| Cursor | opus, sonnet, gpt-5.4, gemini-3-pro, grok-code, composer-2 | Yes |
| Codex | gpt-5.4, gpt-5.3-codex-spark | No |
| OpenCode | 75+ (provider-agnostic via Models.dev) | Yes |

---

## 能力评分参考

评估新平台接入时的能力覆盖度:

| 等级 | 覆盖率 | 判定 |
|------|--------|------|
| A+ | 10/10 core + 4/4 ext + 5/5 hooks + 15+/17 features | 完全兼容 |
| A | 10/10 core + 5/5 hooks + 10+/17 features | 高度兼容 |
| B | 8+/10 core + 3+/5 hooks + 5+/17 features | 推荐接入 |
| C | 6+/10 core + 1+/5 hooks + 1+/17 features | 有条件接入（需降级方案） |
| D | <6/10 core 或 0 hooks | 不建议接入 |
