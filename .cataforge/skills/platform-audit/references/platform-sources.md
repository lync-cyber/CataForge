# 平台文档检索策略

检索各 AI IDE 的最新文档时使用以下搜索词和优先源。

> 文档 URL 会随版本更新变化，以下地址仅作为起始参考。如链接失效，用搜索词重新定位。

---

## Claude Code (Anthropic)

### 搜索词
- `"Claude Code" tools hooks settings.json 2026`
- `"Claude Code" PreToolUse PostToolUse hook configuration`
- `"Claude Code" agent subagent model tools frontmatter`
- `"Claude Code" agent teams multi-agent coordination`
- `"Claude Code" memory skills isolation worktree`
- `"Claude Code" permissionMode auto bypassPermissions`
- `"Claude Code" scheduled tasks CronCreate RemoteTrigger`
- `"Claude Code" plugin marketplace skills`
- `site:code.claude.com`
- `site:github.com anthropics/claude-code`
- `"Claude Code" MCP server configuration .mcp.json`
- `"Claude Code" CLI commands flags`

### ctx7 查询
```bash
npx ctx7@latest library "claude code" "hooks tools agent settings"
```

### 优先源
1. Claude Code 官方文档站 (code.claude.com/docs)
2. GitHub: anthropics/claude-code (README, CHANGELOG)
3. Claude Code 内置 `/help` 输出

### 关注点
- `.claude/settings.json` 中的 hook 配置结构
- agent frontmatter 支持的字段（17 个字段全集，含 memory, effort, isolation, color, skills, hooks, mcpServers 等）
- Agent Teams 功能（experimental）
- `.mcp.json` 格式
- 环境变量名（CLAUDE_PROJECT_DIR 等）
- Permission modes（6 种: default, acceptEdits, auto, dontAsk, bypassPermissions, plan）
- 模型选择（opus, sonnet, haiku + full model ID）
- Plugin 系统
- Scheduled tasks / background agents

---

## Cursor

### 搜索词
- `Cursor IDE tools hooks configuration 2026`
- `Cursor preToolUse postToolUse hooks.json`
- `Cursor agent Task dispatch configuration`
- `Cursor cloud agents computer use automations`
- `Cursor parallel agents worktree`
- `Cursor autonomy slider tab compose agent`
- `Cursor BugBot autofix MCP apps`
- `Cursor team marketplace plugins`
- `site:cursor.com`
- `site:docs.cursor.com hooks`
- `Cursor rules .cursor/rules MDC format`
- `Cursor MCP server configuration`
- `Cursor Shell Read Write Glob Grep tool names`

### ctx7 查询
```bash
npx ctx7@latest library "cursor" "hooks tools agent rules"
```

### 优先源
1. Cursor 官方文档 (cursor.com/features, cursor.com/changelog)
2. Cursor changelog / release notes
3. Cursor Forum (forum.cursor.com)

### 关注点
- `.cursor/hooks.json` 格式和支持的事件（camelCase: preToolUse, postToolUse, stop, sessionStart）
- 工具名称拼写（Shell, Read, Write, Glob, Grep, WebSearch, Task）
- `.cursor/rules/` MDC 规则格式
- file_edit 和 file_write 是否仍共用 Write 工具
- user_question (Ask Questions) 是否已稳定
- Cloud Agents: isolated VM, computer use, video recording
- Automations: event/schedule triggers (GitHub, Slack, Linear, webhook)
- Parallel Agents: up to 8 concurrent, worktree isolation
- Autonomy slider: Tab → edit → full agent
- Permission modes: default, auto
- Model selection: multi-provider (OpenAI, Anthropic, Gemini, xAI, Cursor)
- Team Marketplace: private plugin repos

---

## Codex (OpenAI)

### 搜索词
- `OpenAI Codex CLI tools hooks 2026`
- `Codex CLI hooks.json PreToolUse PostToolUse`
- `Codex CLI agent spawn_agent TOML format`
- `Codex CLI cloud tasks parallel background`
- `Codex CLI computer use sandbox`
- `Codex CLI realtime voice WebRTC`
- `Codex CLI plugin system MCP`
- `Codex CLI resume session`
- `Codex CLI approval modes auto read-only full-access`
- `site:developers.openai.com/codex`
- `site:github.com openai/codex`
- `Codex CLI sandbox apply_patch shell`
- `Codex CLI config.toml MCP configuration`
- `Codex CLI developer_instructions agent format`

### ctx7 查询
```bash
npx ctx7@latest library "openai codex" "CLI hooks agent tools"
```

### 优先源
1. OpenAI Codex 文档站 (developers.openai.com/codex)
2. GitHub: openai/codex (README, docs/, releases)
3. npm package 文档 (`npm info @openai/codex`)

### 关注点
- `.codex/hooks.json` 格式和支持的事件
- hook matcher 使用 `Bash`（不是 `shell`）— tool_overrides 关键
- agent TOML 格式中的字段名（`developer_instructions` 不是 `instructions`）
- `.codex/config.toml` 中 `[mcp_servers.<id>]` 格式
- 上下文窗口大小和默认模型
- 沙箱模式（sandbox_mode 字段, OS-level firewall）
- spawn_agent + wait_agent 异步调度模式
- Cloud tasks: `codex cloud` with --attempts best-of-N
- Computer use: native capability
- Realtime voice: WebRTC v2
- Plugin system: installable bundles
- Session resume: /resume, codex resume
- Approval modes: auto (default), read-only, full-access
- Multi-root: --add-dir

---

## OpenCode

### 搜索词
- `OpenCode AI IDE tools hooks 2026`
- `OpenCode plugin system hooks events`
- `OpenCode agent skills MCP custom tools`
- `OpenCode GitHub Actions CI/CD integration`
- `OpenCode session review git-backed`
- `OpenCode plan mode build mode`
- `OpenCode multi-model providers Models.dev`
- `site:opencode.ai`
- `site:github.com opencode-ai/opencode`
- `OpenCode agent task dispatch configuration`
- `OpenCode opencode.json configuration`
- `OpenCode MCP server integration`

### ctx7 查询
```bash
npx ctx7@latest library "opencode" "AI IDE tools hooks agent"
```

### 优先源
1. OpenCode 官方文档站 (opencode.ai/docs)
2. GitHub: opencode-ai/opencode (README, docs/)
3. npm/Go module 文档

### 关注点
- 工具名称小写风格（read, bash, task, websearch, webfetch, question）
- Plugin 系统和 hook 事件（tool.execute.before, tool.execute.after, session.created, session.idle）
- Hook 通过 JS/TS plugin 实现，config_format 为 `plugin`
- `opencode.json` 配置格式
- agent 定义是否仍使用 yaml-frontmatter
- 是否新增原生 hook 支持（可能从 plugin → native）
- Agent skills: SKILL.md, on-demand loading
- Custom tools: config-defined, any language
- GitHub Actions: `opencode github install/run`
- Git-backed session review
- Plan mode vs Build mode
- Multi-provider: 75+ models via Models.dev
- Plugin marketplace: npm + local
- ACP (Agent Context Protocol) support
- LSP server integration

---

## 新平台调研

对于未知平台，按以下模板搜索:

### 通用搜索词模板
```
"<platform name>" AI IDE tools available 2026
"<platform name>" hook lifecycle events configuration
"<platform name>" agent definition format
"<platform name>" CLI SDK API reference
"<platform name>" MCP model context protocol
"<platform name>" plugin extension system
"<platform name>" cloud agent remote execution
"<platform name>" permission approval modes
"<platform name>" model selection routing
site:github.com <org>/<repo>
```

### 评估要点
1. 是否有 function calling / tool use 机制 → core capability mapping
2. 是否有 hook / middleware / lifecycle 事件 → hook event mapping
3. agent 系统: 定义格式、frontmatter 字段、扫描目录、同步/异步 → agent config
4. 配置文件: 格式(JSON/YAML/TOML)、路径、schema
5. MCP 支持: 内置 vs 插件 vs 不支持 → MCP config injection
6. CLI: 是否有命令行工具、可编程性
7. 环境变量: 项目根目录变量名
8. 沙箱: 是否有隔离执行环境
9. 高级特性: cloud agents, parallel execution, scheduled tasks, computer use, etc. → features
10. 权限模型: 审批模式、安全策略 → permissions
11. 模型路由: 可用模型、per-agent 选择 → model_routing
12. Agent 高级配置: memory, skills, isolation, etc. → agent_config
