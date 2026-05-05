# 速查卡

> 一页纸速查：平台能力 + CLI 命令 + 产物路径。详细说明见各深链。
>
> **适用版本**：v0.1.15。

## 平台能力速览

| 能力 | Claude Code | Cursor | CodeX | OpenCode |
|------|:---:|:---:|:---:|:---:|
| Agent | 原生 | 原生 | TOML | 规则注入 |
| Hook | 原生 | 原生 | 仅 Bash | rules_injection 降级 |
| MCP | 原生 | 原生 | 原生 | 原生 |
| 指令文件 | `CLAUDE.md` | `AGENTS.md` + `.mdc` | `AGENTS.md` | `opencode.json` + `AGENTS.md` |
| 上下文自动注入 | `@` eager | `.mdc alwaysApply` | 层级 `AGENTS.md`（32 KiB） | `opencode.json.instructions` |
| 并行 Agent | ✓ | ✓（8 并发） | ✓（best-of-N） | 有限 |
| Worktree 隔离 | ✓ | ✓ | — | — |

→ [`../guide/platforms.md`](../guide/platforms.md) · [`../architecture/platform-adaptation.md`](../architecture/platform-adaptation.md)

## 产物落盘路径

| 平台 | 指令文件 | Agent | Hook | Rules | MCP |
|------|---------|-------|------|-------|-----|
| claude-code | `CLAUDE.md` | `.claude/agents/*.md` | `.claude/settings.json` | `.claude/rules/` | `.mcp.json` |
| cursor | `AGENTS.md` | `.cursor/agents/*/AGENT.md` | `.cursor/hooks.json` | `.cursor/rules/*.mdc` | `.cursor/mcp.json` |
| codex | `AGENTS.md` | `.codex/agents/*.toml` | `.codex/hooks.json`（仅 Bash） | — | `.codex/config.toml`（`[mcp_servers.<id>]`） |
| opencode | `AGENTS.md` + `opencode.json` | `.opencode/agents/*.md` | `.opencode/plugins/*.ts`（需手包装） | 注册到 `opencode.json.instructions` | `opencode.json`（`mcp.<id>`） |

## CLI 速查

| 命令 | 用途 | 详见 |
|------|-----|------|
| `cataforge doctor` | 环境健康诊断 / CI gate | [cli#doctor](./cli.md#doctor) |
| `cataforge setup --platform <id>` | 初始化 `.cataforge/`、定平台 | [cli#setup](./cli.md#setup) |
| `cataforge deploy [--dry-run]` | 投放 IDE 产物 | [cli#deploy](./cli.md#deploy) |
| `cataforge agent list / validate` | Agent 发现与校验 | [cli#agent](./cli.md#agent) |
| `cataforge skill list / run <id>` | Skill 发现与执行 | [cli#skill](./cli.md#skill) |
| `cataforge hook list / test <n>` | Hook 列表 / 单项测试 | [cli#hook](./cli.md#hook) |
| `cataforge mcp list / start / stop` | MCP 生命周期 | [cli#mcp](./cli.md#mcp) |
| `cataforge plugin list` | 插件发现 | [cli#plugin](./cli.md#plugin) |
| `cataforge upgrade check` | 对比包版本 vs scaffold 版本 | [cli#upgrade](./cli.md#upgrade) |
| `cataforge upgrade apply [--dry-run]` | 刷新 scaffold（自动快照） | [upgrade.md](../guide/upgrade.md) |
| `cataforge upgrade rollback [--list] [--from <ts>]` | 从快照回滚 | [upgrade.md](../guide/upgrade.md#快照与回滚) |
| `cataforge upgrade verify` | `doctor` 别名 | [cli#upgrade](./cli.md#upgrade) |
| `cataforge docs list / load <ref>` | 文档索引与段落加载 | [cli#docs](./cli.md#docs) |
| `cataforge event log` | 写事件日志 | [cli.md](./cli.md) |
| `cataforge correction record --deviation <type>` | 写 On-Correction Learning 偏离日志 | [cli#correction](./cli.md#correction) |
| `cataforge feedback bug \| suggest \| correction-export` | 把下游信号打包为上游可消费的 markdown 反馈（`--print` / `--out` / `--clip` / `--gh`） | [cli#feedback](./cli.md#feedback) |

## 配置速查

| 文件 | 位置 | 用户可编辑字段 |
|------|------|---------------|
| `framework.json` | `.cataforge/framework.json` | `runtime.platform` · `runtime.mode` · `runtime.checkpoints` · `upgrade.state` |
| `PROJECT-STATE.md` | `.cataforge/PROJECT-STATE.md` | 整个文件 |
| `profile.yaml` | `.cataforge/platforms/<id>/profile.yaml` | 能力声明、降级策略、`context_injection` |
| `hooks.yaml` | `.cataforge/hooks/hooks.yaml` | hook 规范（平台无关） |

完整字段表：[`configuration.md`](./configuration.md)

## 退出码

| 码 | 含义 |
|---|------|
| `0`  | 成功 |
| `1`  | 业务失败 |
| `2`  | Click 用法错误 |
| `70` | 路线图 stub（未实现） |
