# 平台审计检查清单

审计每个平台时，逐一核对以下维度。标记 OK / CHANGED / NEW / REMOVED / N/A。

---

## 1. Core Tool Mapping (tool_map)

10 个核心 Capability ID 与平台原生工具名称的映射:

| # | Capability ID | 检查项 | 备注 |
|---|--------------|--------|------|
| 1 | `file_read` | 工具名是否变更？是否仍存在？ | 注意大小写 |
| 2 | `file_write` | 工具名是否变更？是否与 file_edit 合并？ | Cursor v3 合并为 Write |
| 3 | `file_edit` | 工具名是否变更？编辑语义是否改变？ | 有的平台用 diff/patch |
| 4 | `file_glob` | 是否新增支持？工具名？ | 部分平台无独立 glob 工具 |
| 5 | `file_grep` | 是否新增支持？工具名？ | 部分平台通过 shell 实现 |
| 6 | `shell_exec` | 工具名是否变更？沙箱限制变化？ | 注意 hook matcher 可能不同 |
| 7 | `web_search` | 是否新增/移除支持？ | 部分平台不提供 |
| 8 | `web_fetch` | 是否新增/移除支持？ | 部分平台不提供 |
| 9 | `user_question` | 是否新增/稳定化？异步平台可能不支持 | 可选能力 |
| 10 | `agent_dispatch` | 工具名/调度方式是否变更？ | 同步 vs 异步 |

### 检查方法
1. 查阅平台最新文档中的 tool/function 列表
2. 对比当前 profile.yaml 中 tool_map 的每个条目
3. 特别注意: 工具**重命名**（功能不变但名称改了）是最隐蔽的兼容性问题

---

## 2. Extended Capabilities (extended_capabilities)

4 个扩展能力与平台原生工具/特性的映射:

| # | Capability ID | 检查项 | 备注 |
|---|--------------|--------|------|
| 1 | `notebook_edit` | 平台是否提供 notebook 编辑工具？ | Claude Code: NotebookEdit |
| 2 | `browser_preview` | 平台是否提供浏览器自动化/预览？ | Claude Code: Preview MCP, Cursor: Computer Use |
| 3 | `image_input` | 平台是否支持图片/截图输入？ | Codex: -i flag, OpenCode: drag-drop |
| 4 | `code_review` | 平台是否有专用代码审查工具？ | Codex: /review |

### 扩展原则
- 当新工具出现在 2+ 平台上，应作为新的 extended capability 添加
- 当某个 extended capability 被 3+ 平台支持时，考虑提升为核心 capability
- 新增 key 无需修改 adapter 代码 — `get_extended_tool_map()` 自动读取

---

## 3. Agent Configuration (agent_config)

### 3a. Supported Frontmatter Fields

17 个标准 agent frontmatter 字段:

| # | 字段 | 检查项 | 备注 |
|---|------|--------|------|
| 1 | `name` | 是否仍为必需？命名规则变化？ | 通常全平台支持 |
| 2 | `description` | 是否仍为必需？ | 通常全平台支持 |
| 3 | `tools` | 格式变化？allowlist 语义？ | 注意 Agent(type) 语法 |
| 4 | `disallowedTools` | 是否新增支持？ | 部分平台不支持 denylist |
| 5 | `model` | 值格式变化？新增模型别名？ | alias vs full model ID |
| 6 | `permissionMode` | 新增模式？模式名变更？ | 平台特有模式 |
| 7 | `maxTurns` | 是否新增支持？ | 部分平台不支持 |
| 8 | `skills` | 是否新增支持？注入 vs 引用？ | Claude Code: inject content |
| 9 | `mcpServers` | inline 定义 vs 引用？格式变化？ | 注意 transport 类型 |
| 10 | `hooks` | agent-scoped hooks？格式？ | Claude Code 支持完整 |
| 11 | `memory` | scope 变化？目录结构？ | user/project/local |
| 12 | `background` | 是否新增支持？ | 后台运行标志 |
| 13 | `effort` | 值范围变化？ | low/medium/high/max |
| 14 | `isolation` | 新增隔离模式？ | worktree |
| 15 | `color` | 颜色选项变化？ | UI 显示 |
| 16 | `initialPrompt` | 是否新增支持？ | 自动提交首条消息 |
| 17 | `prompt` | CLI --agents JSON 用 | 等价于 body |

### 3b. Memory Scopes

| scope | 说明 | 检查项 |
|-------|------|--------|
| `user` | 跨项目全局 | 目录路径？`~/.claude/agent-memory/<name>/` |
| `project` | 项目级（可 git 追踪） | 目录路径？`.claude/agent-memory/<name>/` |
| `local` | 项目级（不追踪） | 目录路径？`.claude/agent-memory-local/<name>/` |

### 3c. Isolation Modes

| mode | 说明 | 检查项 |
|------|------|--------|
| `worktree` | Git worktree 隔离 | 是否仍支持？自动清理行为？ |

---

## 4. Platform Features (features)

17 个平台级功能特性:

| # | Feature | 检查项 | 典型平台 |
|---|---------|--------|---------|
| 1 | `cloud_agents` | 远程/云端 agent 执行？ | Cursor Cloud, Codex cloud |
| 2 | `agent_teams` | 多 session agent 协作？ | Claude Code (experimental) |
| 3 | `parallel_agents` | 并发 agent 执行？最大数量？ | Claude Code (10), Cursor (8) |
| 4 | `scheduled_tasks` | 定时/事件触发 agent？ | Claude Code (Cron), Cursor (Automations) |
| 5 | `background_agents` | 后台 agent 执行？ | 多数平台支持 |
| 6 | `plan_mode` | 只读规划模式？ | Claude Code, OpenCode |
| 7 | `computer_use` | 原生 UI/浏览器自动化？ | Cursor, Codex |
| 8 | `realtime_voice` | 语音输入/输出？ | Codex (WebRTC) |
| 9 | `multi_model` | 多模型选择/路由？ | 多数平台支持 |
| 10 | `session_resume` | session 持久化和恢复？ | Codex (/resume), OpenCode (Git-backed) |
| 11 | `worktree_isolation` | Git worktree 隔离？ | Claude Code, Cursor |
| 12 | `autonomy_slider` | 可配置 agent 自治级别？ | Cursor |
| 13 | `ci_cd_integration` | 原生 CI/CD 集成？ | OpenCode (GitHub Actions) |
| 14 | `multi_root` | 多项目工作区？ | Codex (--add-dir) |
| 15 | `agent_memory` | Agent 级跨 session 持久化记忆？ | Claude Code |
| 16 | `plugin_marketplace` | Plugin 发现和安装？ | 多数平台支持 |
| 17 | `context_management` | 上下文窗口管理（章节、压缩）？ | Claude Code |

### 检查方法
1. 查阅平台最新版本的 changelog 和功能文档
2. 对比当前 profile.yaml 中 features 的每个条目
3. 新增平台特性应及时反映为 true
4. 已移除特性应标记为 false

---

## 5. Hook Events (hooks.event_map)

5 个标准事件与平台事件名的映射:

| # | 标准事件 | 检查项 |
|---|---------|--------|
| 1 | `PreToolUse` | 平台事件名？触发时机？matcher 支持哪些工具？ |
| 2 | `PostToolUse` | 平台事件名？是否携带工具输出？ |
| 3 | `Stop` | 平台事件名？任务完成 vs 中断的区分？ |
| 4 | `SessionStart` | 平台事件名？触发时机？ |
| 5 | `Notification` | 平台事件名？权限通知机制？ |

### 检查方法
1. 查阅平台 hook/lifecycle 文档
2. 关注事件名的大小写（Claude Code 用 PascalCase，Cursor 用 camelCase）
3. 检查新增事件是否可映射到 CataForge 标准事件

---

## 6. Hook Tool Overrides (hooks.tool_overrides)

当平台的 hook matcher 使用的工具名称与 tool_map 不同时需要配置:

| 检查项 | 说明 |
|--------|------|
| tool_map 工具名 vs hook matcher 工具名 | 是否一致？ |
| 新增的 override | 是否有新的不一致？ |
| 已有 override 是否仍需要 | 平台更新后可能已统一 |

### 典型案例
- Codex: `tool_map.shell_exec = "shell"` 但 hook PreToolUse matcher 使用 `"Bash"`
- 需配置 `hooks.tool_overrides.shell_exec: Bash`

---

## 7. Hook Degradation (hooks.degradation)

每个 hook 脚本在该平台的可用性:

| hook 脚本 | 检查项 |
|----------|--------|
| `guard_dangerous` | PreToolUse + shell_exec matcher 是否支持？ |
| `log_agent_dispatch` | PreToolUse + agent_dispatch matcher 是否支持？ |
| `validate_agent_result` | PostToolUse + agent_dispatch matcher 是否支持？ |
| `lint_format` | PostToolUse + file_edit matcher 是否支持？ |
| `detect_correction` | PreToolUse + user_question matcher 是否支持？ |
| `notify_done` | Stop 事件是否支持？ |
| `notify_permission` | Notification 事件是否支持？ |
| `session_context` | SessionStart 事件是否支持？ |

### 判定规则
- 事件存在 + matcher 存在 → `native`
- 事件存在但 matcher 不存在 → `degraded`（仅事件触发，无工具过滤）
- 事件不存在 → `degraded`（需规则注入或 prompt 指令替代）

---

## 8. Agent Definition (agent_definition)

| 检查项 | 说明 |
|--------|------|
| `format` | yaml-frontmatter / toml / json — 是否变更？ |
| `scan_dirs` | 平台扫描 agent 定义的目录路径 |
| `needs_deploy` | 是否需要 CataForge 主动部署（vs 平台自动发现） |
| frontmatter 字段 | 支持的字段名变化（如 Codex 用 `developer_instructions`） |

---

## 9. Dispatch (dispatch)

| 检查项 | 说明 |
|--------|------|
| `tool_name` | 调度使用的工具名称 |
| `is_async` | 是否为异步调度（需要 wait 步骤） |
| `params` | 参数名列表是否变更 |
| 同步/异步模式 | 是否增加了新的调度模式 |

---

## 10. Permissions (permissions)

| 检查项 | 说明 |
|--------|------|
| `modes` | 支持的审批模式列表 |
| 新增模式 | 平台是否新增了审批模式？ |
| 模式语义变化 | 已有模式的行为是否改变？ |

### 跨平台审批模式参考
| 模式 | Claude Code | Cursor | Codex | OpenCode |
|------|------------|--------|-------|----------|
| default | ✓ | ✓ | - | ✓ |
| acceptEdits | ✓ | - | - | - |
| auto | ✓ | ✓ | ✓ | - |
| dontAsk | ✓ | - | - | - |
| bypassPermissions | ✓ | - | - | - |
| plan | ✓ | - | - | - |
| read_only | - | - | ✓ | - |
| full_access | - | - | ✓ | - |

---

## 11. Model Routing (model_routing)

| 检查项 | 说明 |
|--------|------|
| `available_models` | 可用模型列表是否变更？ |
| `per_agent_model` | 是否支持 agent 级别模型选择？ |
| 新增模型 | 平台是否新增了模型选项？ |
| 模型别名 | 别名格式是否变化？（如 opus vs claude-opus-4-6） |

---

## 12. Override Templates

检查 `.cataforge/platforms/<id>/overrides/` 下的模板文件:

| 文件 | 检查项 |
|------|--------|
| `dispatch-prompt.md` | OVERRIDE 块中的工具名称、上下文窗口、模型名称是否最新 |
| `rules/auto-safety-degradation.md` | 降级规则是否与最新 degradation 状态一致 |

---

## 13. MCP 配置

| 检查项 | 说明 |
|--------|------|
| 配置文件格式 | JSON / TOML — 是否变更 |
| 配置文件路径 | `.mcp.json` / `.codex/config.toml` 等 |
| server 配置结构 | 字段名/嵌套结构是否变更 |
| transport 类型 | stdio / http / sse / ws — 新增类型？ |
| 高级功能 | resource reads, elicitations, outputSchema 等 |

---

## 14. 沙箱/Sandbox

| 检查项 | 说明 |
|--------|------|
| 沙箱模式 | 是否新增沙箱/容器化执行 |
| 文件系统限制 | 是否有读写权限变化 |
| 网络限制 | 是否影响 MCP / webhook |

---

## 15. CLI / SDK

| 检查项 | 说明 |
|--------|------|
| CLI 命令变更 | 新增/移除/重命名的命令 |
| SDK API 变更 | 编程接口变化 |
| 配置文件格式 | 全局/项目配置结构变化 |

---

## 16. 源码影响矩阵

差异发现后，确定需要修改的源码文件:

| 差异类型 | 需更新的文件 |
|---------|-------------|
| tool_map 变更 | `profile.yaml`, `test_platform.py`, `test_translator.py`, `test_hook_bridge.py` |
| extended_capabilities 变更 | `profile.yaml` |
| agent_config 变更 | `profile.yaml` |
| features 变更 | `profile.yaml` |
| permissions 变更 | `profile.yaml` |
| model_routing 变更 | `profile.yaml` |
| hook event 变更 | `profile.yaml`, `test_hook_bridge.py` |
| tool_overrides 变更 | `profile.yaml`, `bridge.py`, `test_hook_bridge.py` |
| degradation 变更 | `profile.yaml` |
| agent format 变更 | `profile.yaml`, `<platform>.py`, `test_deployer_refactor.py` |
| dispatch 变更 | `profile.yaml`, `dispatch-prompt.md` |
| 新增核心 Capability | `types.py`, `conformance.py`, 所有 `profile.yaml` |
| 新增扩展 Capability | `types.py`, 所有 `profile.yaml` |
| 新增 Agent 字段 | `types.py`, 支持该字段的 `profile.yaml` |
| 新增 Platform Feature | `types.py`, 所有 `profile.yaml` |
| 新增 PermissionMode | `types.py`, 支持该模式的 `profile.yaml` |
| 可选能力变更 | `types.py`, `conformance.py`, `test_conformance.py` |
| 上下文/模型变更 | `dispatch-prompt.md`, `profile.yaml` |
