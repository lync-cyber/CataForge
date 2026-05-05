# 故障排查

> 按症状索引的常见问题。跑不通时先在这里查；仍无法解决的请用 `cataforge feedback bug --gh`（v0.3.0 起，自动聚合 `cataforge --version` + `doctor` + 最近 `EVENT-LOG` + `upstream-gap` corrections + `framework-review` FAIL 摘要）开 [GitHub Issues](https://github.com/lync-cyber/CataForge/issues)。需要手工填模板时，至少带上 `cataforge doctor` 完整输出。

## 目录

- [安装与环境](#安装与环境)
- [CLI 乱码](#cli-乱码)
- [找不到 `.cataforge/` 或命令入口](#找不到-cataforge-或命令入口)
- [Agent / Skill 列表为空](#agent--skill-列表为空)
- [IDE 内看不到 Agent / Rules](#ide-内看不到-agent--rules)
- [MCP 启动失败](#mcp-启动失败)
- [Hook 不触发或没有回显](#hook-不触发或没有回显)
- [升级后 AGENT.md 或 Hook 脚本不见了](#升级后-agentmd-或-hook-脚本不见了)
- [登录态异常](#登录态异常)

---

## 安装与环境

**`python` 找不到（Windows）。** 优先用 `py -3.12 -m venv .venv`，绕过 Windows Store 的 `python.exe` 别名。

**PowerShell 激活 venv 报执行策略错误。** 执行 `Set-ExecutionPolicy -Scope Process RemoteSigned` 一次性放行当前 shell；或改用 `cmd.exe`。

**`pip install` 超时。** 换国内镜像后重试（如清华、阿里）。

**`uv tool install cataforge` 后 CLI 找不到。** 执行 `uv tool update-shell` 并重开终端，更新 PATH。

## CLI 乱码

CLI 启动时已自动切 UTF-8。若仍乱码，通常是**终端渲染**问题：

- Windows Terminal / PowerShell：`chcp 65001`，或切换到全覆盖 Unicode 的字体。
- 兜底：`set PYTHONUTF8=1`（PowerShell: `$env:PYTHONUTF8="1"`）后重开终端。

## 找不到 `.cataforge/` 或命令入口

- `deploy` / `doctor` 必须在项目根执行。用 `cataforge doctor` 的 `project_root:` 行确认解析到了正确目录。
- PATH 中找不到 `cataforge`：`which cataforge`（Git Bash）/ `where cataforge`（cmd）/ `Get-Command cataforge`（PowerShell）定位安装位置。

## Agent / Skill 列表为空

- 不在项目根运行：`cd` 到含 `.cataforge/` 的目录重跑。
- `.cataforge/agents/*/AGENT.md` 缺失：跑 `cataforge agent validate`，按报错补文件。

## IDE 内看不到 Agent / Rules

1. 确认执行了**真部署**（`cataforge deploy`），而非 `--dry-run`。
2. 按平台重新检查：
   - Claude Code：`git status -u` 应列出新增的 `.claude/agents/*.md` 与 `CLAUDE.md`。
   - Cursor：`File → Reload Window` 强制重载规则；设置 → `Rules for AI` 应列出 `.cursor/rules/*.mdc`。
   - CodeX / OpenCode：重启 CLI 进程后再观察。

## MCP 启动失败

- `cataforge mcp list` 找不到 id：检查文件是否位于 `.cataforge/mcp/*.yaml`。
- `start` 报错 `command not found`：`command` 不在 PATH，或 `env:` 缺必需变量。
- IDE 内看不到 server：确认真部署把 MCP 合并进了对应配置文件（Claude Code `.mcp.json`、Cursor `.cursor/mcp.json`、CodeX `.codex/config.toml`、OpenCode `opencode.json`）。

## Hook 不触发或没有回显

- 对照平台 profile 的 `degradation:` 段：标记为 `degraded` 的事件本就没有原生触发。
- **OpenCode**：原生不支持 hook 事件，需把脚本包装为 `.opencode/plugins/<id>.ts`；否则只有 `rules_injection` 降级生效。
- **Claude Code**：检查 `.claude/settings.json` 的 `hooks.*` 是否被部署写入。
- **CodeX**：仅 `Bash` matcher 生效，其它动作看不到 hook 属于预期。

## 升级后 AGENT.md 或 Hook 脚本不见了

`cataforge upgrade apply` 会整体覆盖 `.cataforge/` 下除 `framework.json` 保留字段和 `PROJECT-STATE.md` 以外的文件。但 apply 前已自动快照到 `.cataforge/.backups/<ts>/`：

```bash
cataforge upgrade rollback --list                    # 找回最近的快照
cataforge upgrade rollback --from <ts> --yes         # 恢复它
```

长期方案：把自定义 agent / hook 放到 `.cataforge/plugins/`（不会被覆盖），或直接提交到项目 `docs/`、`scripts/` 下。

## 登录态异常

**先在 IDE 内独立跑通一次"Hello"对话再回到 CataForge 验证。** 鉴权失败不是 CataForge 的问题，但容易被误判成部署问题。

| IDE | 如何确认已登录 |
|-----|--------------|
| Claude Code | `/login` 后不再弹登录提示 |
| Cursor | 左下角可见账号头像 |
| CodeX | `codex` 启动后不再提示鉴权 |
| OpenCode | `opencode auth list` 能列出凭证 |
