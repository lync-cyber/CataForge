# 常见问题

> 按主题分组的高频问题。若未覆盖到你的场景，请在 [GitHub Issues](https://github.com/lync-cyber/CataForge/issues) 提问。

## 安装与环境

### Q：Python 版本要求？

`>=3.10`，已验证 3.10 / 3.11 / 3.12 / 3.13 / 3.14；3.14 free-threaded（PEP 703）未系统验证。

### Q：Windows 下 `python` 找不到？

优先用 `py -3.12 -m venv .venv`，绕过 Windows Store 的 `python.exe` 别名。详见 [`getting-started/installation.md`](./getting-started/installation.md) §Windows 最小可跑清单。

### Q：PowerShell 激活 venv 报执行策略错误？

`Set-ExecutionPolicy -Scope Process RemoteSigned` 一次性放行当前 shell；永久放行改 `-Scope CurrentUser`（生产机不建议）。

### Q：CLI 出现乱码怎么办？

CLI 启动时已自动切 UTF-8。若仍乱码通常是**终端渲染**问题：

- Windows Terminal / PowerShell：`chcp 65001`，或切换到支持 Unicode 的字体。
- 兜底：`set PYTHONUTF8=1` 后重开终端。

---

## 基础使用

### Q：`deploy` 找不到 `.cataforge/`？

必须在项目根执行。用 `cataforge doctor` 查看 `project_root` 是否正确。

### Q：`agent list` / `skill list` 返回空？

- 不在项目根运行，或 `.cataforge/agents/*/AGENT.md` 缺失。
- 运行 `cataforge agent validate` 看具体报错。

### Q：`cataforge deploy` 和 `cataforge setup --deploy` 有什么区别？

自 v0.1.2 起：

- `setup` 默认**只初始化**脚手架，不写 IDE 产物。
- `deploy` 才把 agent / rule / hook / MCP 实际落盘。
- `setup --deploy` 是兼容 v0.1.1 行为的别名。

### Q：多次 `deploy` 会不会污染 IDE 目录？

不会。`deploy` 幂等，且自动清理上次留下的孤儿（详见 [`architecture/platform-adaptation.md`](./architecture/platform-adaptation.md) §6）。

---

## 平台相关

### Q：Cursor 部署为什么会碰到 `.claude/` 目录？

**默认不会**。仅当 `.cataforge/platforms/cursor/profile.yaml` 的 `rules.cross_platform_mirror` 为 `true` 时才会写 `.claude/rules` 镜像。干运行会明示 `SKIP:` 提示。

### Q：CodeX 里 hook 不生效？

CodeX 的 hooks **仅支持 `Bash` matcher**（其它事件降级），这是 profile 的 `partial`。非 Bash 动作看不到 hook 回显属于预期。

### Q：OpenCode 的 hook 要怎么启用？

OpenCode 原生不支持 hook，框架默认降级为 `rules_injection`。若需原生 hook 事件，需将脚本包装为 `.opencode/plugins/*.ts`。

### Q：能否同一个仓库同时用 Cursor + Claude Code？

可以。把 `.cataforge/platforms/cursor/profile.yaml` 的 `rules.cross_platform_mirror` 改为 `true`，`deploy` 会额外写入 `.claude/rules` 镜像。

---

## 升级

### Q：`upgrade check` 报 scaffold outdated 但我不想刷新？

跳过 `upgrade apply` 即可，CataForge 不会强制刷新。保守策略下新版本 CLI 对旧 scaffold 仍兼容。

### Q：`upgrade apply` 会覆盖我的 `PROJECT-STATE.md` 吗？

**不会**。保留字段列表详见 [`guide/upgrade.md`](./guide/upgrade.md) §字段保留规则。

---

## TDD 与工作流

### Q：TDD 引擎的 `light` 模式和 `standard` 什么时候自动切换？

按微任务 LOC 预判：

- `< TDD_LIGHT_LOC_THRESHOLD`（默认 50）→ light（RED+GREEN 合并）
- `≥` 阈值 → standard（三步独立）

### Q：REFACTOR 失败会丢代码吗？

不会。状态回滚为 `rolled-back`，保留 GREEN 阶段产出。失败被记录到 `EVENT-LOG.jsonl` 供 `reflector` 分析。

### Q：Sprint Review 多久触发一次？

默认每 `SPRINT_REVIEW_MICRO_TASK_COUNT=3` 个微任务触发一次，可在 `framework.json` 的 `constants` 调整。

---

## MCP

### Q：`cataforge mcp start` 报 `command not found`？

`command` 不在 `PATH`，或环境变量缺失。检查 `.cataforge/mcp/<id>.yaml` 中的 `command` 与 `env` 字段。

### Q：IDE 内看不到 MCP server？

确认**真部署**（不是 `--check`）已把 MCP 合并到平台配置文件：

- Claude Code: `.mcp.json`
- Cursor: `.cursor/mcp.json`
- CodeX: `.codex/config.toml`（`[mcp_servers.<id>]`）
- OpenCode: `opencode.json`（`mcp.<id>`）

---

## 其它

### Q：如何贡献？

见 [`contributing.md`](./contributing.md)。

### Q：去哪里报 bug / 提需求？

[GitHub Issues](https://github.com/lync-cyber/CataForge/issues)。优先使用 issue 模板，附带 `cataforge doctor` 完整输出。

### Q：这个项目和其它 Agent 框架有什么不同？

核心差异：**同一套 `.cataforge/` 规范驱动 4 个 IDE**，而非锁定单一平台。详见 [`README.md`](../README.md) §项目定位。
