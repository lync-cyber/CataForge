# Platform Capability Matrix

本文档列出 CataForge 四个平台的类型化 capability 映射。每个绑定都显式声明：

- `tool`：平台原生工具名；不支持时为 `null`
- `kind`：`native` / `replacement` / `unsupported`
- `availability.any_of`：可选的运行时可用条件
- `hook_matchers`：模型工具名与 hook payload matcher 不同时的显式映射

deploy 生成的 `.cataforge/state/<platform>/capability-report.json` 是当前项目的最终解析结果；ownership manifest 不承载能力语义。

## tool_map（核心工具能力）

| capability | claude-code | cursor | codex | opencode |
|---|---|---|---|---|
| `file_read` | `Read` · native | `Read` · native | `shell` · replacement | `read` · native |
| `file_write` | `Write` · native | `Write` · native | `apply_patch` · native | `write` · native |
| `file_edit` | `Edit` · native | `Write` · native | `apply_patch` · native | `edit` · native |
| `file_glob` | `Glob` · native | `Glob` · native | `shell` · replacement | `glob` · native |
| `file_grep` | `Grep` · native | `Grep` · native | `shell` · replacement | `grep` · native |
| `shell_exec` | `Bash` · native | `Shell` · native | `shell` · native | `bash` · native |
| `web_search` | `WebSearch` · native | `WebSearch` · native | `web_search` · native | `websearch` · native |
| `web_fetch` | `WebFetch` · native | unsupported | `shell` · replacement | `webfetch` · native |
| `user_question` | `AskUserQuestion` · native | unsupported | `request_user_input` · conditional native | `question` · native |
| `agent_dispatch` | `Agent` · native | `Task` · native | `spawn_agent` · native | `task` · native |

Codex `user_question` 仅在 root thread 可用：

- Plan 模式：原生可用
- Default 模式：仅启用 `default_mode_request_user_input` feature 后可用
- subagent：不可用

CataForge 不自动开启实验 feature。无 `CapabilityContext` 时，解析结果为 `conditional`，而不是错误地标成无条件 native。

## extended_capabilities（扩展能力）

| capability | claude-code | cursor | codex | opencode |
|---|---|---|---|---|
| `notebook_edit` | `NotebookEdit` · native | unsupported | unsupported | unsupported |
| `browser_preview` | `preview_start` · replacement | `computer` · native | unsupported | unsupported |
| `image_input` | `Read` · native | unsupported | `image` · native | `image` · native |
| `code_review` | unsupported | unsupported | `review` · native | unsupported |

## Hook 策略

平台 profile 的 `hooks.policies.<script>` 负责声明运行方式：

| mode | 行为 |
|---|---|
| `native` | 只生成平台原生 hook |
| `hybrid` | 生成原生 hook，同时部署部分或等价 fallback |
| `degraded` | 不生成原生 hook，只部署 fallback |
| `unsupported` | 不生成资产，输出显式诊断 |

| hook | claude-code | cursor | codex | opencode |
|---|---|---|---|---|
| `detect_correction` | native | degraded + `rules_injection`（partial） | **hybrid：原生 `PostToolUse(request_user_input)` + `prompt_instruction`（partial）** | native |
| `notify_permission` | native | degraded + `skip`（none） | native `PermissionRequest` | degraded + `skip`（none） |

Codex 非托管 hook 仍须在 `/hooks` 中审查信任；hook 定义变化后需要重新信任。

## Agent 工具权限

Agent frontmatter 使用 canonical capability id。`agent_config.tool_policy` 决定平台能否执行权限意图：

- `allow_deny`：支持 allow 与 deny；同一原生工具等价类内的混合决策直接报错。
- `allow_only`：只编译 allow；deny 记录为 `unenforced`。
- `inherit_only`：不生成伪造的 per-agent allow/deny。Codex 使用此模式，继承父任务工具与权限。

Codex 只有在能够证明 agent 禁止全部写能力时，才把该 agent 编译为 `sandbox_mode = "read-only"`；其它限制均在 capability report 中标为 `unenforced`。不得使用 hooks、command rules 或不存在的 TOML 字段冒充完整的 per-agent 权限隔离。
