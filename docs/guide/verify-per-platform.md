<!-- 变更原因：从 manual-verification.md 拆出 §2 分平台 6 步操作；专注于 How-to，避免与 Tutorial / Reference 混写 -->
# 手动验证 · 分平台步骤

> 本文是 [`manual-verification.md`](./manual-verification.md) 五步流水线 §VERIFY 的展开。每个平台共 6 步：`初始化 → 干运行 → 真部署 → IDE 内观测 → 清理/回滚 → 判定`。
>
> 真部署会写入工作区。开始前先 `git status` 留一个干净起点，事后可用下方各 §Step 5 的命令清理。

## 目录

- [Claude Code](#claude-code)
- [Cursor](#cursor)
- [CodeX](#codex)
- [OpenCode](#opencode)

---

## Claude Code

### Step 1 — 初始化

```bash
cataforge setup --platform claude-code
```

预期：`Platform set to: claude-code` + `Setup complete. Run cataforge deploy ...`

> 自 v0.1.2 起，`setup` 只初始化 `.cataforge/` 脚手架与记录目标平台，不再自动写入 IDE 产物。若需旧版一步到位的行为，加 `--deploy`。`--no-deploy` 已弃用（v0.3 移除），不需要显式传入。

### Step 2 — 干运行

```bash
cataforge deploy --dry-run --platform claude-code
```

预期（节选）：

```text
would write CLAUDE.md ← PROJECT-STATE.md
would write .claude/agents/orchestrator.md
would merge mcpServers.<id> → ...\.mcp.json      # 若声明了 MCP
Deploy complete.
```

### Step 3 — 真部署

```bash
cataforge deploy --platform claude-code
# Deploy 产物默认被 .gitignore 排除（有意为之）。用 -u/--ignored 审阅完整清单：
git status -u
# 或直接列文件：
ls -la CLAUDE.md .mcp.json .claude/
```

预期落盘：`CLAUDE.md`、`.claude/agents/*.md`（扁平布局，v0.1.2 起）、`.claude/settings.json`（hook）、`.mcp.json`（若有 MCP）。

### Step 4 — IDE 内观测

```bash
cd <project-root>
claude                    # 启动 Claude Code
```

在 Claude Code 会话中依次确认：

| 观测项 | 操作 | 应看到 |
|-------|------|-------|
| 指令文件加载 | `/memory` 或首响回显 | `CLAUDE.md` 被读入 |
| 上下文注入 | 查看 `CLAUDE.md` 第一行 | `@.cataforge/rules/COMMON-RULES.md`（Claude Code 在会话启动时自动展开） |
| 规则展开验证 | 问 Claude："COMMON-RULES 第几节定义 MAX_QUESTIONS_PER_BATCH？" | 直接答出 §框架配置常量、值为 3，证明 `@path` 已 eager 加载 |
| Sub-agent 发现 | `/agents` | 至少 `orchestrator`、`implementer` 等 |
| Hook 触发 | 跑一次 Bash（如 `ls`） | `.claude/settings.json` 中配置的 `PreToolUse` / `PostToolUse` 日志 |
| MCP 注册 | `/mcp` | 声明的 MCP server 出现在列表 |

### Step 4a — 上下文个性化部署验证

Deploy 期会按 `profile.yaml.context_injection` 的声明为当前平台烘焙上下文加载方式。Claude Code 预期产物：

```bash
head -1 CLAUDE.md
# 预期输出（首行）：@.cataforge/rules/COMMON-RULES.md
```

```bash
head -3 CLAUDE.md
# 预期：
# @.cataforge/rules/COMMON-RULES.md
#
# # 项目状态
```

若首行不是 `@` 引用，检查：

- `.cataforge/platforms/claude-code/profile.yaml` 是否含 `context_injection.auto_injection.preamble_files`
- 该列表是否包含 `.cataforge/rules/COMMON-RULES.md`
- `inline_file_syntax.kind` 是否为 `at_mention`（若改成 `read_tool` 则 preamble 会被跳过——这是预期行为）

> 与 Codex / OpenCode 对比：Codex 的 `AGENTS.md` 首行不含 `@`（无 `@` 语法），规则加载走 `dispatch-prompt.md` 里的 "请先 Read" 指令；OpenCode 首行也不含 `@`，但 `opencode.json.instructions` 会注册 `AGENTS.md` + `.cataforge/rules/*.md` 供平台自动加载。

### Step 5 — 清理 / 回滚

Deploy 产物（`CLAUDE.md` / `.mcp.json` / `.claude/agents/` / `.claude/rules/`）默认在 `.gitignore` 内，因此 `git restore` 找不到它们，`git clean -fd` 也不会动被忽略目录。按下列命令彻底清理：

```bash
rm -f CLAUDE.md .mcp.json .cataforge/.deploy-state
rm -rf .claude/agents .claude/rules .claude/skills \
       .claude/commands .claude/settings.json
```

> 若想回到 scaffold-only 状态（保留 `.cataforge/` 但清光 IDE 产物），上述命令之后再跑一次 `cataforge setup --platform claude-code`（不带 `--deploy`）即可。

### Step 6 — 判定

初始化 / 干运行 / 真部署 / IDE 内四项观测均通过即视为合格。任一失败查 [`../getting-started/troubleshooting.md`](../getting-started/troubleshooting.md) 定位。

---

## Cursor

### Step 1 — 初始化

```bash
cataforge setup --platform cursor
```

> 自 v0.1.2 起，默认 Cursor 部署不再触及 `.claude/` 目录。`.cursor/rules/*.mdc` 是 Cursor 原生消费的规则文件；历史版本额外镜像一份 Markdown 到 `.claude/rules` 以兼容 Claude Code 双栖使用，现改为可选。若仓库确实同时用 Cursor + Claude Code 共享同一套 prompt，去 `.cataforge/platforms/cursor/profile.yaml` 把 `rules.cross_platform_mirror` 改为 `true`。

### Step 2 — 干运行

```bash
cataforge deploy --dry-run --platform cursor
```

预期（节选）：`.cursor/hooks.json`、`.cursor/rules/*.mdc`、`SKIP: detect_correction`（降级提示）、`SKIP: .claude/rules Markdown mirror (enable via profile rules.cross_platform_mirror: true)`（镜像默认关闭）。

### Step 3 — 真部署

```bash
cataforge deploy --platform cursor
```

预期落盘（默认配置）：`AGENTS.md`、`.cursor/agents/*/AGENT.md`、`.cursor/hooks.json`、`.cursor/rules/*.mdc`、`.cursor/mcp.json`（若有 MCP）。不会出现 `.claude/` 下任何文件。若打开了 `rules.cross_platform_mirror`，额外出现 `.claude/rules`（软链 / junction / 拷贝，视 OS 而定）。

### Step 4 — IDE 内观测

打开 Cursor → `File / Open Folder` → 选中项目根目录。

| 观测项 | 操作 | 应看到 |
|-------|------|-------|
| Rules 加载 | 设置 → Rules for AI（或 `.cursorrules` 标签） | `.cursor/rules/*.mdc` 被列出并处于启用态 |
| Agents 发现 | 聊天面板的 agent 选择器 | `.cursor/agents/` 下的 agent 可选 |
| Hook 生效 | 触发一次文件编辑 | Cursor 控制台 / 状态栏有 PreToolUse / PostToolUse 痕迹 |
| MCP 注册 | 设置 → MCP Servers | `.cursor/mcp.json` 中声明的 server 已列出 |

> `AskUserQuestion` 与 `Notification` 在 Cursor 上降级（profile 标 `degraded`），这是预期，不是缺陷。

### Step 5 — 清理

```bash
git restore --source=HEAD --staged --worktree AGENTS.md
git clean -fd .cursor
# 仅在你打开了 rules.cross_platform_mirror 时需要下面这行：
# rm -rf .claude/rules
```

### Step 6 — 判定

出现 `.cursor/hooks.json` + `.cursor/rules/*.mdc` + Cursor 设置里能看到 rules / mcp 即合格。同时确认项目根下没有 `.claude/` 目录（若打开镜像则允许出现 `.claude/rules`）。

---

## CodeX

### Step 1 — 初始化

```bash
cataforge setup --platform codex
```

### Step 2 — 干运行

```bash
cataforge deploy --dry-run --platform codex
```

预期（节选）：`AGENTS.md`、`.codex/agents/*.toml`、`.codex/hooks.json`、`.codex/config.toml` 的 `mcp_servers.<id>` 合并。

### Step 3 — 真部署

```bash
cataforge deploy --platform codex
```

### Step 4 — IDE 内观测

```bash
cd <project-root>
codex
```

| 观测项 | 操作 | 应看到 |
|-------|------|-------|
| AGENTS.md 读入 | 开启会话 | Codex 首响提及或遵循 `AGENTS.md` 内容 |
| Agents 发现 | `/agent` 或 `spawn_agent` | `.codex/agents/*.toml` 声明的 agent 可调度 |
| Hook 生效 | 让它跑一条 Bash（`echo ok`） | `.codex/hooks.json` PreToolUse 回显触发 |
| MCP 注册 | `/mcp` 或 status 面板 | `.codex/config.toml` 下 `[mcp_servers.<id>]` 生效 |

> CodeX 的 hooks 仅支持 `Bash` matcher（其它事件降级），这是 profile 的 `partial`；非 Bash 动作看不到 hook 回显属于预期。

### Step 5 — 清理

```bash
git restore --source=HEAD --staged --worktree AGENTS.md
git clean -fd .codex
```

### Step 6 — 判定

`AGENTS.md` + `.codex/config.toml` 的 `[mcp_servers.*]` + Codex 会话行为一致 → 合格。

---

## OpenCode

### Step 1 — 初始化

```bash
cataforge setup --platform opencode
```

### Step 2 — 干运行

```bash
cataforge deploy --dry-run --platform opencode
```

预期（节选）：`.opencode/agents/*.md`、`opencode.json` 的 `mcp.<id>` 合并、若干 `SKIP:` 降级提示、`would write rules_injection`。

### Step 3 — 真部署

```bash
cataforge deploy --platform opencode
```

### Step 4 — IDE 内观测

```bash
cd <project-root>
opencode
```

| 观测项 | 操作 | 应看到 |
|-------|------|-------|
| AGENTS.md 读入 | 开启会话 | 首响遵循 `AGENTS.md` 指令 |
| Agents 发现 | 调度 sub-agent | `.opencode/agents/*.md` 可被 `task` 工具使用 |
| 规则注入 | 首响或 system context | 降级注入的规则（CataForge rules_injection）生效 |
| MCP 注册 | 在线状态 / 会话内 `mcp` 列表 | `opencode.json` 下 `mcp.<id>` 生效 |

> OpenCode hooks 需要写成 JS/TS 插件（`.opencode/plugins/`），所有事件标 `degraded`。若未自行包装插件，hook 不会在 IDE 中触发——这是预期。

### Step 5 — 清理

```bash
git restore --source=HEAD --staged --worktree AGENTS.md opencode.json
git clean -fd .opencode
```

### Step 6 — 判定

`.opencode/agents/*.md` + `opencode.json` 含 `mcp.<id>` + 会话能识别 `AGENTS.md` → 合格。

---

## 参考

- 流水线总览：[`manual-verification.md`](./manual-verification.md)
- 平台能力差异：[`platforms.md`](./platforms.md)
- 专题验证（Hook / MCP / 自动化回归 / 升级幂等）：[`verify-topics.md`](./verify-topics.md)
- 标准测试用例：[`verify-cases.md`](./verify-cases.md)
- 故障排查：[`../getting-started/troubleshooting.md`](../getting-started/troubleshooting.md)
