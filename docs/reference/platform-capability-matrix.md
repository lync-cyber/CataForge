# Platform Capability Matrix

本文档列出 CataForge 支持的四个平台对各 capability 的原生映射。`null` 表示该平台无原生工具/能力，deploy 时会被 `PlatformAdapter.resolve_tools_list` 过滤并触发一次性 WARN（见 [src/cataforge/adapter/platform/base.py](../../src/cataforge/adapter/platform/base.py) `resolve_tools_list`）。

> 数据来源：`.cataforge/platforms/{platform}/profile.yaml`。

## tool_map（核心工具能力）

| capability | claude-code | cursor | codex | opencode |
|---|---|---|---|---|
| `file_read` | `Read` | `Read` | `shell` | `read` |
| `file_write` | `Write` | `Write` | `apply_patch` | `write` |
| `file_edit` | `Edit` | `Write` | `apply_patch` | `edit` |
| `file_glob` | `Glob` | `Glob` | `shell` | `glob` |
| `file_grep` | `Grep` | `Grep` | `shell` | `grep` |
| `shell_exec` | `Bash` | `Shell` | `shell` | `bash` |
| `web_search` | `WebSearch` | `WebSearch` | `web_search` | `websearch` |
| `web_fetch` | `WebFetch` | **`null`** | `shell` | `webfetch` |
| `user_question` | `AskUserQuestion` | **`null`** | **`null`** | `question` |
| `agent_dispatch` | `Agent` | `Task` | `spawn_agent` | `task` |

## extended_capabilities（扩展能力）

| capability | claude-code | cursor | codex | opencode |
|---|---|---|---|---|
| `notebook_edit` | `NotebookEdit` | **`null`** | **`null`** | **`null`** |
| `browser_preview` | `preview_start`（MCP） | `computer` | **`null`** | **`null`** |
| `image_input` | `Read` | **`null`** | `image` | `image` |
| `code_review` | **`null`** | **`null`** | `review` | **`null`** |

## Hook 降级

deploy 读取 [.cataforge/hooks/hooks.yaml](../../.cataforge/hooks/hooks.yaml) 后按 `profile.yaml#hooks.degradation` 解析；`native` 表示直接生成平台 hook 配置，`degraded` 表示走 `degradation_templates` 中的降级策略。当前实装策略集合（`rules_injection` / `prompt_instruction` / `prompt_checklist` / `skip`）与各自输出文件的语义见 [hook-degradation-strategies.md](hook-degradation-strategies.md)。

下表仅列出"至少有一个平台 degraded"的 hook；未列出的 hook（`guard_dangerous` / `notify_done` / `session_context`）在四个平台都是 `native`。

| hook | strategy | claude-code | cursor | codex | opencode |
|---|---|---|---|---|---|
| `log_agent_dispatch` | `prompt_instruction` | native | native | degraded → `auto-prompt-instructions.md` | native |
| `validate_agent_result` | `prompt_checklist` | native | native | degraded → `auto-prompt-checklists.md` | native |
| `lint_format` | `skip` | native | native | degraded → skip | native |
| `detect_correction` | `skip` | native | degraded → skip + alwaysApply rule（见 [overrides/rules/correction-record.md](../../.cataforge/platforms/cursor/overrides/rules/correction-record.md)） | degraded → skip | native |
| `detect_review_flag` | `skip` | native | native | degraded → skip（依赖 agent_dispatch 的 PostToolUse 匹配，codex 无 agent matcher 不触发） | native |
| `notify_permission` | `skip` | native | degraded → skip | degraded → skip | degraded → skip（OpenCode 无 Notification 事件） |

**Codex 平台注**：`prompt_instruction` / `prompt_checklist` 写到 `.cataforge/platforms/codex/overrides/rules/` 后**当前不自动注入** agent 上下文（`profile.yaml#context_injection.rules_distribution.activation: manual_read`）；文件存在、deploy 有日志，但要让 Codex agent 真正读到这些规则需扩展 codex.py 的 AGENTS.md 注入逻辑。

## Agent 端如何使用

Agent frontmatter 的 `tools.allow` / `tools.deny` 使用 capability id（不是平台工具名）。deploy 时按当前平台 `tool_map` 解析为原生工具名：

- 当前平台映射为非 `null` → 工具名进入 agent 配置
- 映射为 `null` → 工具被静默丢弃，deploy 末尾发一条聚合 WARN 列出所有被丢弃的 capability

如果某 capability 对你的工作流是硬依赖（例如某 agent 必须能 `user_question`），可在 agent 端通过 `disable-model-invocation` 或 platform-specific overrides 处理；不要在 profile.yaml 把 `null` 改成虚构工具名 —— 后者会让 hook 触发匹配失效。
