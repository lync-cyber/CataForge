# Manual Verification Guide

本指南带你从 **0** 出发，在 Claude Code / Cursor / CodeX / OpenCode 四个 IDE 下完整安装、部署并**在 IDE 内真实跑通** CataForge，验证其核心能力是否按预期工作。

<p align="center">
  <img src="../assets/verification-flow.svg" alt="CataForge 手动验证五步流水线" width="100%">
</p>

## 目录

- [0. 本指南的使用方法](#0-本指南的使用方法)
- [1. 前置准备](#1-前置准备)
  - [1.1 系统要求](#11-系统要求)
  - [1.2 安装 CataForge](#12-安装-cataforge)
  - [1.3 安装目标 IDE 客户端](#13-安装目标-ide-客户端)
  - [1.4 健康检查](#14-健康检查)
- [2. 分 IDE 端到端验证](#2-分-ide-端到端验证)
  - [2.1 Claude Code](#21-claude-code)
  - [2.2 Cursor](#22-cursor)
  - [2.3 CodeX](#23-codex)
  - [2.4 OpenCode](#24-opencode)
- [3. 专题验证](#3-专题验证)
  - [3.1 Hook 生效观察](#31-hook-生效观察)
  - [3.2 MCP 生命周期与 IDE 接线](#32-mcp-生命周期与-ide-接线)
  - [3.3 Agent / Skill 发现](#33-agent--skill-发现)
  - [3.4 自动化回归](#34-自动化回归)
  - [3.5 升级与 scaffold 刷新](#35-升级与-scaffold-刷新)
  - [3.6 Deploy 幂等与孤儿清理](#36-deploy-幂等与孤儿清理)
- [4. 标准测试用例](#4-标准测试用例)
- [5. 故障排查](#5-故障排查)
- [6. 验证结果反馈模板](#6-验证结果反馈模板)

---

## 0. 本指南的使用方法

### 验证目标

| # | 目标 | 判定依据 |
|---|------|---------|
| 1 | **平台适配** | 同一套 `.cataforge/` 可切到 4 个 IDE |
| 2 | **部署编排** | `deploy` 生成对应 IDE 的产物并可合并已有配置 |
| 3 | **能力发现** | `agent list` / `skill list` / `hook list` 稳定运行 |
| 4 | **Hook 桥接** | `hooks.yaml` → 平台 hook 配置，降级可见 |
| 5 | **MCP 生命周期** | 声明可发现，start/stop 可控 |
| 6 | **IDE 内生效** | 在 IDE 真实会话中能看到 Agent / Rules / Hook / MCP 被加载 |
| 7 | **回归通过** | `pytest -q` 全量通过 |

### 适用读者

- **评估者 / 贡献者**：想先从零跑通一遍再决定是否深入。
- **迁移团队**：需要在多 IDE 间切换同一套工作流。
- **验收方**：复现环境、出具 Verification Report。

### 五步验证法

按 **FIG. 01** 顺序执行；任何一步不通过都应回到上一步而非跳过：

1. **INSTALL** — 装好 Python、CataForge、IDE 客户端。
2. **SETUP** — `cataforge setup --platform <ide>` 切到目标平台。
3. **DRY-RUN** — `deploy --dry-run` 预览产物，核对无误。
4. **DEPLOY** — `cataforge deploy` 实际写入 IDE 产物。
5. **VERIFY** — 启动 IDE，在真实会话中观测 Agent / Hook / MCP 被使用。

> 原指南只覆盖 1–3 步。本版本补齐 4–5 步，使"验证"不再只是 CLI 自测。

---

## 1. 前置准备

### 1.1 系统要求

| 条件 | 版本 / 说明 |
|------|-------------|
| OS | Windows 10+ / macOS 12+ / Linux（主流发行版） |
| Python | **`>=3.10`**（必需）；已验证 3.10 / 3.11 / 3.12 / 3.13 / 3.14；3.14 free-threaded（PEP 703）未系统验证 |
| pip 或 uv | `pip>=23`；或 `uv>=0.4`（推荐） |
| Git | 近期版本（CataForge 依赖 git 元信息） |
| 可选工具 | `ruff`、`docker`、`npx` — `doctor` 会检测但不强制 |

> CLI 启动时已自动切换 stdout/stderr 到 UTF-8（`cataforge.utils.common.ensure_utf8_stdio`）。**多数情形下无需** 手动设置 `PYTHONUTF8=1` 或 `chcp 65001`；若仍在 legacy 代码页（cp936/cp1252）下出现 `UnicodeEncodeError`，参照 [`../getting-started/troubleshooting.md`](../getting-started/troubleshooting.md) §CLI 乱码。

### 1.2 安装 CataForge

完整安装方式（uv tool / 项目 venv / 纯 pip / Windows 最小清单）见 [`../getting-started/installation.md`](../getting-started/installation.md)。本指南后续步骤假设你已跑通 `cataforge --version`。

> **若要跑 §3.4 的 `pytest -q`** — 必须使用"项目 venv + `uv pip install -e '.[dev]'`"方式安装，`uv tool install` 的全局 CLI 环境里没有 `pytest` 等测试依赖。

### 1.3 安装目标 IDE 客户端

先看清 **FIG. 02**：`deploy` 会为每个 IDE 写入的文件与原生支持程度一目了然。

<p align="center">
  <img src="../assets/artifact-map.svg" alt="CataForge 四平台部署产物对照图" width="100%">
</p>

下表为四个 IDE 的常见安装渠道与最小可用校验。**具体命令以各 IDE 官方文档为准**，CataForge 不随版本绑定客户端。

| IDE | 常见安装渠道 | 最小可用校验 |
|-----|-------------|-------------|
| **Claude Code** | `npm i -g @anthropic-ai/claude-code`（官方 npm 包） | 终端跑 `claude --version` 能输出版本号；首次需登录 Anthropic 账号 |
| **Cursor** | 从 [cursor.com](https://cursor.com) 下载桌面客户端（Windows/macOS/Linux） | 能打开客户端、完成登录；命令面板可见 "Cursor: ..." 命令 |
| **CodeX** | 通过 OpenAI Codex CLI 官方渠道安装（典型为 `npm i -g @openai/codex`） | 终端跑 `codex --version`；首次需 OpenAI 鉴权 |
| **OpenCode** | 从 [opencode.ai](https://opencode.ai) 获取安装命令（npm / curl 脚本）| 终端跑 `opencode --version`；按其指引配置模型 provider |

> **Claude Code / CodeX / OpenCode** 均为 CLI，启动方式是 `cd` 到项目根目录后执行客户端命令。**Cursor** 是 GUI，"打开文件夹"指向项目根目录即可。

#### 1.3.1 登录态与鉴权

| IDE | 鉴权需求 | 怎样确认已登录 |
|-----|---------|---------------|
| Claude Code | Anthropic 账号（`/login` 或首次启动引导） | 启动后不再弹登录提示 |
| Cursor | Cursor 账号（GUI 引导） | 左下角可见账号头像 |
| CodeX | OpenAI API Key 或官方登录 | `codex` 启动后不再提示鉴权 |
| OpenCode | 依据所选 provider（OpenAI / Anthropic / 其它） | `opencode auth list`（或类似）能列出凭证 |

> 鉴权失败不是 CataForge 的问题；先在 IDE 里独立跑通一次"Hello"对话再回来做部署验证。

### 1.4 健康检查

```bash
cataforge doctor
```

**预期（Expected）**

- 末行：`Diagnostics complete.`
- `framework.json` / `hooks.yaml` 标记 `OK`
- `claude-code / cursor / codex / opencode` 四个 profile 均 `OK`
- `Framework migration checks` 段显示 `N/N passed`（可能伴随 `M skipped`）；**退出码 0**
- 任一 FAIL 时退出码 1（可用于 CI gate）
- 未 deploy 前，依赖 IDE 产物的检查（如 `mc-0.7.0-detect-correction-registered`）会 **SKIP**，不会 FAIL，保证 fresh install 流程 `doctor` 不卡壳

**失败提示（Troubleshoot）**

- 当前目录非含 `.cataforge/` 的项目根 → `cd` 到项目根重跑。
- 缺 `PyYAML`/`click` → 确认用的是第 1.2 步装好的环境。
- Windows 下命令找不到 → `which cataforge`（Git Bash）/ `where cataforge`（cmd）检查 PATH。

---

## 2. 分 IDE 端到端验证

> 每个平台共 **6 步**：`初始化 → 干运行 → 真部署 → IDE 内观测 → 清理/回滚 → 判定`。
> 真部署会写入工作区，记得先用 `git status` 留一个干净起点，事后可用 `git clean` 回滚。

### 2.1 Claude Code

#### Step 1 — 初始化

```bash
cataforge setup --platform claude-code
```

**预期**：`Platform set to: claude-code` + `Setup complete. Run cataforge deploy ...`

> 自 v0.1.2 起，`setup` 只初始化 `.cataforge/` 脚手架、记录目标平台，**不再**自动写入 IDE 产物。若需旧版一步到位的行为，加 `--deploy`。`--no-deploy` 已弃用（v0.3 移除），不需要显式传入。

#### Step 2 — 干运行

```bash
cataforge deploy --dry-run --platform claude-code
```

**预期**（节选）：

```text
would write CLAUDE.md ← PROJECT-STATE.md
would write .claude/agents/orchestrator.md
would merge mcpServers.<id> → ...\.mcp.json      # 若声明了 MCP
Deploy complete.
```

#### Step 3 — 真部署

```bash
cataforge deploy --platform claude-code
# Deploy 产物默认被 .gitignore 排除（有意为之）。用 -u/--ignored 审阅完整清单：
git status -u
# 或直接列文件：
ls -la CLAUDE.md .mcp.json .claude/
```

**预期落盘**：`CLAUDE.md`、`.claude/agents/*.md`（扁平布局，v0.1.2 起）、`.claude/settings.json`（hook）、`.mcp.json`（若有 MCP）。

#### Step 4 — IDE 内观测

```bash
cd <project-root>
claude                    # 启动 Claude Code
```

在 Claude Code 会话中依次确认：

| 观测项 | 操作 | 应看到 |
|-------|------|-------|
| 指令文件加载 | `/memory` 或首响回显 | `CLAUDE.md` 被读入 |
| **上下文注入** | 查看 `CLAUDE.md` 第一行 | **`@.cataforge/rules/COMMON-RULES.md`**（Claude Code 会在会话启动时自动展开该文件，无需子代理 Read） |
| **规则展开验证** | 问 Claude："COMMON-RULES 第几节定义 MAX_QUESTIONS_PER_BATCH？" | 能直接回答"§框架配置常量"且值为 3，证明 `@path` 已 eager 加载 |
| Sub-agent 发现 | `/agents` | 至少 `orchestrator`、`implementer` 等 |
| Hook 触发 | 执行一次 Bash（例如让它跑 `ls`） | `.claude/settings.json` 中配置的 `PreToolUse` / `PostToolUse` 日志 |
| MCP 注册 | `/mcp` | 声明的 MCP server 出现在列表 |

#### Step 4a — 上下文个性化部署验证

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

#### Step 5 — 清理 / 回滚

Deploy 产物（`CLAUDE.md` / `.mcp.json` / `.claude/agents/` / `.claude/rules/`）默认在 `.gitignore` 内，因此 `git restore` 找不到它们，`git clean -fd` 也不会动被忽略目录。按下列命令彻底清理：

```bash
rm -f CLAUDE.md .mcp.json .cataforge/.deploy-state
rm -rf .claude/agents .claude/rules .claude/skills \
       .claude/commands .claude/settings.json
```

> 若想回到 **scaffold-only** 状态（保留 `.cataforge/` 但清光 IDE 产物），上述命令之后再跑一次 `cataforge setup --platform claude-code`（不带 `--deploy`）即可。

#### Step 6 — 判定

初始化 / 干运行 / 真部署 / IDE 内四项观测均通过即视为合格。任一失败对照 §5 定位。

---

### 2.2 Cursor

#### Step 1 — 初始化

```bash
cataforge setup --platform cursor
```

> **自 v0.1.2 起**：默认 Cursor 部署**不再触及 `.claude/` 目录**。`.cursor/rules/*.mdc` 是 Cursor 原生消费的规则文件；历史版本额外镜像一份 Markdown 到 `.claude/rules` 以兼容 Claude Code 双栖使用，现改为可选。若你的仓库确实同时用 Cursor + Claude Code 共享同一套 prompt，去 `.cataforge/platforms/cursor/profile.yaml` 把 `rules.cross_platform_mirror` 改为 `true`。

#### Step 2 — 干运行

```bash
cataforge deploy --dry-run --platform cursor
```

**预期**（节选）：`.cursor/hooks.json`、`.cursor/rules/*.mdc`、`SKIP: detect_correction`（降级提示）、`SKIP: .claude/rules Markdown mirror (enable via profile rules.cross_platform_mirror: true)`（镜像已默认关闭的提示）。

#### Step 3 — 真部署

```bash
cataforge deploy --platform cursor
```

**预期落盘**（默认配置）：`AGENTS.md`、`.cursor/agents/*/AGENT.md`、`.cursor/hooks.json`、`.cursor/rules/*.mdc`、`.cursor/mcp.json`（若有 MCP）。**不会出现 `.claude/` 下任何文件。** 若打开了 `rules.cross_platform_mirror`，额外出现 `.claude/rules`（软链 / junction / 拷贝，视 OS 而定）。

#### Step 4 — IDE 内观测

打开 Cursor → `File / Open Folder` → 选中项目根目录。

| 观测项 | 操作 | 应看到 |
|-------|------|-------|
| Rules 加载 | 设置 → **Rules for AI**（或 `.cursorrules` 标签） | `.cursor/rules/*.mdc` 被列出并处于启用态 |
| Agents 发现 | 聊天面板的 agent 选择器 | `.cursor/agents/` 下的 agent 可选 |
| Hook 生效 | 触发一次文件编辑 | Cursor 控制台 / 状态栏有 PreToolUse / PostToolUse 痕迹 |
| MCP 注册 | 设置 → **MCP Servers** | `.cursor/mcp.json` 中声明的 server 已列出 |

> `AskUserQuestion` 与 `Notification` 在 Cursor 上降级（profile 标 `degraded`），这是预期，不是缺陷。

#### Step 5 — 清理

```bash
git restore --source=HEAD --staged --worktree AGENTS.md
git clean -fd .cursor
# 仅在你打开了 rules.cross_platform_mirror 时需要下面这行：
# rm -rf .claude/rules
```

#### Step 6 — 判定

出现 `.cursor/hooks.json` + `.cursor/rules/*.mdc` + Cursor 设置里能看到 rules/mcp 即合格。同时确认项目根下 **没有** `.claude/` 目录（若打开镜像则允许出现 `.claude/rules`）。

---

### 2.3 CodeX

#### Step 1 — 初始化

```bash
cataforge setup --platform codex
```

#### Step 2 — 干运行

```bash
cataforge deploy --dry-run --platform codex
```

**预期**（节选）：`AGENTS.md`、`.codex/agents/*.toml`、`.codex/hooks.json`、`.codex/config.toml` 的 `mcp_servers.<id>` 合并。

#### Step 3 — 真部署

```bash
cataforge deploy --platform codex
```

#### Step 4 — IDE 内观测

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

#### Step 5 — 清理

```bash
git restore --source=HEAD --staged --worktree AGENTS.md
git clean -fd .codex
```

#### Step 6 — 判定

`AGENTS.md` + `.codex/config.toml` 的 `[mcp_servers.*]` + Codex 会话行为一致 → 合格。

---

### 2.4 OpenCode

#### Step 1 — 初始化

```bash
cataforge setup --platform opencode
```

#### Step 2 — 干运行

```bash
cataforge deploy --dry-run --platform opencode
```

**预期**（节选）：`.opencode/agents/*.md`、`opencode.json` 的 `mcp.<id>` 合并、若干 `SKIP:` 降级提示、`would write rules_injection`。

#### Step 3 — 真部署

```bash
cataforge deploy --platform opencode
```

#### Step 4 — IDE 内观测

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

> **OpenCode hooks 需要写成 JS/TS 插件**（`.opencode/plugins/`），所有事件标 `degraded`。若未自行包装插件，hook 不会在 IDE 中触发 — 这是预期。

#### Step 5 — 清理

```bash
git restore --source=HEAD --staged --worktree AGENTS.md opencode.json
git clean -fd .opencode
```

#### Step 6 — 判定

`.opencode/agents/*.md` + `opencode.json` 含 `mcp.<id>` + 会话能识别 AGENTS.md → 合格。

---

## 3. 专题验证

### 3.1 Hook 生效观察

```bash
cataforge hook list
```

**预期**：按事件分组列出 `PreToolUse / PostToolUse / Stop / Notification / SessionStart` 条目。

真部署后在 IDE 中触发对应动作（编辑 / Bash / 会话开始）即可观测：

- **Claude Code**：`.claude/settings.json` 中 `hooks.*` 配置的脚本被调用。
- **Cursor**：`.cursor/hooks.json` 由客户端读取。
- **CodeX**：`.codex/hooks.json`，仅 `Bash` matcher。
- **OpenCode**：需将脚本包装为 `.opencode/plugins/<id>.ts`（未包装则仅 `rules_injection` 降级生效）。

### 3.2 MCP 生命周期与 IDE 接线

**注册声明**：

```bash
mkdir -p .cataforge/mcp
cat > .cataforge/mcp/echo.yaml <<'EOF'
id: echo-mcp
name: Echo MCP
description: Test MCP server for lifecycle verification
transport: stdio
command: python
args:
  - -c
  - "import time; time.sleep(60)"
EOF
```

**CLI 生命周期**：

```bash
cataforge mcp list            # echo-mcp 出现
cataforge mcp start echo-mcp  # Started: echo-mcp (pid=...)
cataforge mcp stop echo-mcp   # Stopped: echo-mcp
```

**IDE 接线**（真部署后自动合并到对应配置文件）：

| 平台 | 目标文件 | 键路径 |
|------|---------|-------|
| Claude Code | `.mcp.json` | `mcpServers.<id>` |
| Cursor | `.cursor/mcp.json` | `mcpServers.<id>` |
| CodeX | `.codex/config.toml` | `[mcp_servers.<id>]` |
| OpenCode | `opencode.json` | `mcp.<id>` |

进入对应 IDE 后，用其原生 `/mcp` 或设置面板应看到该 server。

### 3.3 Agent / Skill 发现

```bash
cataforge agent list
cataforge agent validate
cataforge skill list
```

**预期**：

- `agent list` 至少包含 `orchestrator`、`implementer`
- `agent validate` 无 fail 项
- `skill list` 至少包含 `code-review`、`sprint-review`

### 3.4 自动化回归

> **重要**：pytest 必须在 1.2 B/C 方案创建的项目 venv 内执行。若按 A 方案（`uv tool install .`）安装，`cataforge` CLI 可用但 `pytest` 拿不到 `pydantic` / `pyyaml`，13 个测试模块会 `ImportError`。最简单的一次性补救：
>
> ```bash
> uv venv && uv pip install -e ".[dev]"
> source .venv/bin/activate          # Windows: .venv\Scripts\activate
> ```

```bash
pytest -q
```

**基线**：全部用例通过、退出码 `0`。具体数量会随 PR 变化，以 `main` 分支最新 CI 的数字为准。

### 3.5 升级与 scaffold 刷新

CataForge 采用**包管理器驱动**的升级模型 —— 包本身走 `pip` / `uv tool`，项目内 `.cataforge/` 脚手架由 `cataforge setup --force-scaffold` 刷新。不存在"远程自升级"。

`framework.json` 的 `version` 字段在每次 scaffold 写入时由当前安装包的 `cataforge.__version__` **实时戳入**（v0.1.2 起），因此 `upgrade apply` 执行后 `upgrade check` 会立刻报告 "up to date" — 完成真正的闭环。

```bash
# 1) 对比"已安装包版本" vs "项目 scaffold 版本"
cataforge upgrade check

# 2) 升级包本身
pip install --upgrade cataforge    # 或: uv tool upgrade cataforge

# 3) 刷新项目 scaffold（保留用户可编辑字段）
cataforge upgrade apply            # 等价于 setup --force-scaffold（默认不 deploy）
#   --dry-run 可预览会刷新哪些文件

# 4) 再次校验：现在应打印 "Scaffold is up to date with the installed package."
cataforge upgrade check

# 5) 验证迁移检查
cataforge upgrade verify           # 别名: cataforge doctor
```

**`--force-scaffold` 保留的用户字段**（不会被覆盖）：

| 文件 | 保留项 |
|------|-------|
| `framework.json` | `runtime.platform`（用户选的 IDE）、`upgrade.state`（升级状态） |
| `PROJECT-STATE.md` | 整个文件（项目运行手册，用户自行维护） |

其余字段（`constants` / `features` / `migration_checks` / `upgrade.source` / `version`）每次都会用最新 scaffold 覆盖。

### 3.6 Deploy 幂等与孤儿清理

多次 `cataforge deploy` 是幂等的，且会自动清理上次部署留下的孤儿：

- `commands/*.md`：源目录里删除 / 重命名的命令会被 prune
- **Claude Code**（扁平布局）：`.claude/agents/*.md` 中源 `agents/` 已移除的 agent 文件会被 prune
- **Cursor / OpenCode**（嵌套布局）：`.cursor/agents/<name>/` 或 `.opencode/agents/<name>/` 中源 `agents/` 删除的子目录会被 prune（仅删含 `AGENT.md` 的目录，不伤 IDE 原生或用户自建 agent）；子目录内非 `AGENT.md` 的历史文件也会被 prune

无需手动 `git clean -fd .claude/` 再重部署。

---

## 4. 标准测试用例

按优先级执行；前 6 项为必过。✅ 表示建议保留勾选用于 Verification Report。

| # | Case | 命令 | 判定 |
|---|------|------|-----|
| 1 | 环境健康 | `cataforge doctor` | `Diagnostics complete.` 且无 `MISSING` |
| 2 | Agent 发现 | `cataforge agent list` | 条目 > 0 |
| 3 | Skill 发现 | `cataforge skill list` | 条目 > 0 且含 `code-review` |
| 4 | Hook 加载 | `cataforge hook list` | 至少含 `PreToolUse`+`PostToolUse` |
| 5 | Cursor 干运行 | `cataforge deploy --dry-run --platform cursor` | 命中 `hooks.json` + `.mdc` |
| 6 | CodeX 干运行 | `cataforge deploy --dry-run --platform codex` | 命中 `AGENTS.md` + `config.toml` |
| 7 | OpenCode 降级 | `cataforge deploy --dry-run --platform opencode` | 含 `SKIP:` + `rules_injection` |
| 8 | 自动化回归 | `pytest -q` | 退出码 0，全部用例通过 |
| 9 | MCP 生命周期 | 见 §3.2 | `list` / `start` / `stop` 均成功 |
| 10 | IDE 内生效 | §2 各平台 Step 4 | 至少一个 IDE 观测到 Agent+Rules+MCP |

---

## 5. 故障排查

按症状索引的故障排查清单已迁至 [`../getting-started/troubleshooting.md`](../getting-started/troubleshooting.md)。包含安装/环境、CLI 乱码、找不到命令入口、Agent/Skill 为空、IDE 看不到部署产物、MCP、Hook、升级、登录态等场景。

---

## 6. 验证结果反馈模板

> 复制下方模板填写，作为 Verification Report 附在 issue / PR 中。

<details>
<summary>点击展开完整模板</summary>

```md
## CataForge Manual Verification Report

- 日期：
- 验证人：
- 操作系统：
- Python 版本：
- 验证分支 / commit：

### 环境准备
- [ ] venv 创建成功
- [ ] CataForge 安装成功（`cataforge --version` 可用)
- [ ] doctor 通过

### IDE 客户端
- [ ] Claude Code 已登录
- [ ] Cursor 已登录
- [ ] CodeX 已鉴权
- [ ] OpenCode 已配置 provider

### 分 IDE 端到端（§2）
|            | Setup | Dry-run | Deploy | In-IDE Verify |
|------------|:-----:|:-------:|:------:|:-------------:|
| Claude Code|       |         |        |               |
| Cursor     |       |         |        |               |
| CodeX      |       |         |        |               |
| OpenCode   |       |         |        |               |

### 标准测试用例（§4）
- Case 1–10：

### 失败项与日志
- 步骤：
- 实际输出：
- 预期输出：
- 初步定位：

### 改进建议
- 
```

</details>
