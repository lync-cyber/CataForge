# 平台适配机制

> CataForge 通过 `PlatformAdapter` 抽象层屏蔽 IDE 差异。同一份 `.cataforge/` 规范资产经 Adapter 翻译为各平台原生文件。

<p align="center">
  <img src="../assets/adapter-translation.svg" alt="CataForge 平台适配器翻译关系" width="100%">
</p>

## 1. 适配原理

`PlatformAdapter` 是一组接口契约，每个平台（`claude-code` / `cursor` / `codex` / `opencode`）有独立实现：

- **能力声明**：在 `profile.yaml` 中声明原生支持的能力。
- **路径映射**：规范资产 → 平台原生目录（如 `.cataforge/agents/` → `.claude/agents/`）。
- **格式翻译**：规范格式 → 平台原生格式（YAML frontmatter ↔ TOML ↔ 规则注入）。
- **降级策略**：声明无法原生支持时的回退方式。

---

## 2. 平台能力矩阵

| 能力 | Claude Code | Cursor | CodeX | OpenCode |
|------|-------------|--------|-------|----------|
| Agent 定义格式 | YAML frontmatter | YAML frontmatter | TOML | 规则注入 |
| 指令文件 | `CLAUDE.md` | `AGENTS.md` + `.mdc` | `AGENTS.md` | `opencode.json` |
| Agent 调度 | Agent（同步） | Task（同步） | `spawn_agent`（异步） | task（同步） |
| Hook 配置 | `settings.json` | `hooks.json` | `hooks.json`（仅 Bash） | 不支持（降级） |
| MCP 配置 | `.mcp.json` | `.cursor/mcp.json` | `.codex/config.toml` | `opencode.json` |
| 上下文自动注入 | `CLAUDE.md` + `@path` eager 预载 | `.cursor/rules/*.mdc` `alwaysApply:true` | `AGENTS.md` 层级合并（32 KiB 上限） | `opencode.json.instructions` |
| 并行 Agent | 支持 | 支持（8 并发） | 支持（best-of-N） | 有限 |
| Worktree 隔离 | 支持 | 支持 | 不支持 | 不支持 |
| 多模型路由 | opus / sonnet / haiku | opus / sonnet / gpt / gemini | gpt-5.4 / spark | 有限 |

---

## 2a. 上下文注入（`context_injection`）

每个 `profile.yaml` 声明平台如何把规则 / 指令加载进 LLM 上下文。Deploy 期读取这些字段，把差异**烘焙**到静态产物里——运行时 LLM 只看到当前平台已定制好的 markdown，无需再做平台判断。

| 字段 | 作用 |
|------|------|
| `auto_injection.mechanism` | 平台原生自动注入机制：`claude_md` / `agents_md` / `cursor_rules` / `opencode_instructions` / `none` |
| `auto_injection.eager` | 是否在会话启动时就常驻上下文（影响 token 预算决策） |
| `auto_injection.size_limit_bytes` | 平台硬上限（Codex AGENTS.md = 32 768 B） |
| `auto_injection.preamble_files` | 需在指令文件顶部内联引用的文件路径（`@{path}` 前缀） |
| `inline_file_syntax.kind` / `.template` | 引用其它文件的首选语法：`at_mention` / `read_tool` / `xml_preload` |
| `rules_distribution.target` | 规则分发目标（平台规则目录或 `opencode.json`） |
| `rules_distribution.format` / `.activation` | MDC / Markdown / 远程 URL 列表；`always` / `glob` / `manual_read` / `opencode_instructions` |
| `rules_distribution.files` | `opencode_instructions` 模式下注册到 `opencode.json.instructions` 的路径模式 |

**Deploy 期如何消费**：

- `PlatformAdapter.deploy_instruction_files` 读取 `auto_injection.preamble_files`，用 `inline_file_syntax.template` 渲染为 `@.cataforge/rules/COMMON-RULES.md` 之类的前缀，直接写到 `CLAUDE.md` / `AGENTS.md` 顶部。
- `OpenCodeAdapter.deploy_instruction_files` 读取 `rules_distribution.files`，写入 `opencode.json.instructions`——LLM 启动时自动加载，不再让子代理手动 `Read`。
- 未声明 `context_injection` 的旧 profile 继续走默认路径（完全向后兼容）。

---

## 3. 降级策略

当目标平台不支持某能力时，框架自动选用降级策略：

| 策略 | 说明 | 典型场景 |
|------|------|---------|
| **rules_injection** | 将 hook 逻辑注入到规则文件中 | OpenCode 无原生 hook 支持 |
| **skip** | 跳过该功能，记录日志 | CodeX 不支持 `detect_correction` |
| **prompt_check** | 在提示词中加入检查指令 | 部分平台无格式检查 hook |
| **degraded** | 功能可用但能力受限 | Cursor 的 `AskUserQuestion` |

---

## 4. 跨平台目录隔离

每个平台部署只生成**自己命名空间**下的产物（`.claude/` / `.cursor/` / `.codex/` / `.opencode/`），互不干扰。

- **Cursor 部署默认不会触及 `.claude/` 目录**。
- 仅当 `.cataforge/platforms/cursor/profile.yaml` 设置 `rules.cross_platform_mirror: true` 时，才会在 `.claude/rules` 创建 Markdown 镜像，供 "Cursor + Claude Code 双栖" 场景共享 prompt。
- 干运行时明示状态：`SKIP: .claude/rules Markdown mirror`。

---

## 5. 部署流程

`cataforge deploy` 命令执行以下步骤：

```text
1. 加载 framework.json 确定目标平台
2. 加载目标平台 profile.yaml
3. 投放指令文件（PROJECT-STATE.md → CLAUDE.md / AGENTS.md）
4. 投放规则文件（COMMON-RULES.md → 平台规则目录）
5. 翻译并投放 Agent 定义（AGENT.md → 平台 agent 格式）
6. 桥接 Hook 配置（hooks.yaml → 平台 hook 配置）
7. 注入 MCP 配置（mcp/*.yaml → 平台 MCP 配置文件）
8. 处理降级（不支持的功能按策略降级或跳过）
9. 生成平台特定附加输出（如 Cursor 的 .mdc 文件）
10. 清理孤儿产物（上次部署残留的、本次不再生成的文件）
```

支持 `--check` 干运行模式，仅输出预期动作不实际执行。

---

## 6. 部署幂等与孤儿清理

多次 `cataforge deploy` 幂等，自动清理上次部署留下的孤儿：

- `.claude/commands/*.md`（或其它平台对应目录）：源目录删除 / 重命名的命令被 prune
- `.claude/agents/<name>/`：
  - 源 `agents/` 删除的子目录被 prune（仅删含 `AGENT.md` 的目录，不伤 IDE 原生 / 用户自建 agent）
  - 子目录内非 `AGENT.md` 的历史文件被 prune

无需手动 `git clean -fd .claude/` 再重部署。

---

## 参考

- 各平台使用与最小配置：[`../guide/platforms.md`](../guide/platforms.md)
- 架构分层：[`overview.md`](./overview.md)
- 平台 profile 文件规格：[`../reference/configuration.md`](../reference/configuration.md)
