<!-- 变更原因：从 manual-verification.md 拆出 §3 专题验证；按"我想验证 X"组织，纯 How-to -->
# 手动验证 · 专题

> 各专题独立可执行。完成 [`manual-verification.md`](./manual-verification.md) §INSTALL 与 §SETUP 即可开跑。

## 目录

- [Hook 生效观察](#hook-生效观察)
- [MCP 生命周期与 IDE 接线](#mcp-生命周期与-ide-接线)
- [Agent / Skill 发现](#agent--skill-发现)
- [自动化回归](#自动化回归)
- [升级与 scaffold 刷新](#升级与-scaffold-刷新)
- [Deploy 幂等与孤儿清理](#deploy-幂等与孤儿清理)

---

## Hook 生效观察

```bash
cataforge hook list
```

预期：按事件分组列出 `PreToolUse / PostToolUse / Stop / Notification / SessionStart` 条目。

真部署后在 IDE 中触发对应动作（编辑 / Bash / 会话开始）即可观测：

- Claude Code：`.claude/settings.json` 中 `hooks.*` 配置的脚本被调用。
- Cursor：`.cursor/hooks.json` 由客户端读取。
- CodeX：`.codex/hooks.json`，仅 `Bash` matcher。
- OpenCode：需将脚本包装为 `.opencode/plugins/<id>.ts`（未包装则仅 `rules_injection` 降级生效）。

---

## MCP 生命周期与 IDE 接线

### 注册声明

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

### CLI 生命周期

```bash
cataforge mcp list            # echo-mcp 出现
cataforge mcp start echo-mcp  # Started: echo-mcp (pid=...)
cataforge mcp stop echo-mcp   # Stopped: echo-mcp
```

### IDE 接线（真部署后自动合并到对应配置文件）

| 平台 | 目标文件 | 键路径 |
|------|---------|-------|
| Claude Code | `.mcp.json` | `mcpServers.<id>` |
| Cursor | `.cursor/mcp.json` | `mcpServers.<id>` |
| CodeX | `.codex/config.toml` | `[mcp_servers.<id>]` |
| OpenCode | `opencode.json` | `mcp.<id>` |

进入对应 IDE 后，用其原生 `/mcp` 或设置面板应看到该 server。

---

## Agent / Skill 发现

```bash
cataforge agent list
cataforge agent validate
cataforge skill list
```

预期：

- `agent list` 至少包含 `orchestrator`、`implementer`
- `agent validate` 无 fail 项
- `skill list` 至少包含 `code-review`、`sprint-review`

---

## 自动化回归

> 重要：pytest 必须在使用"项目 venv + `uv pip install -e '.[dev]'`"方式创建的环境内执行。若按 `uv tool install .` 方式安装，`cataforge` CLI 可用但 `pytest` 拿不到 `pydantic` / `pyyaml`，13 个测试模块会 `ImportError`。一次性补救：
>
> ```bash
> uv venv && uv pip install -e ".[dev]"
> source .venv/bin/activate          # Windows: .venv\Scripts\activate
> ```

```bash
pytest -q
```

基线：全部用例通过、退出码 `0`。具体数量随 PR 变化，以 `main` 分支最新 CI 数字为准。

---

## 升级与 scaffold 刷新

CataForge 采用包管理器驱动的升级模型——包本身走 `pip` / `uv tool`，项目内 `.cataforge/` 脚手架由 `cataforge upgrade apply` 刷新。不存在"远程自升级"。

`framework.json` 的 `version` 字段在每次 scaffold 写入时由当前安装包的 `cataforge.__version__` 实时戳入（v0.1.2 起），因此 `upgrade apply` 执行后 `upgrade check` 会立刻报告 "up to date" — 完成真正的闭环。

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

`upgrade apply` 保留的用户字段（不会被覆盖）：

| 文件 | 保留项 |
|------|-------|
| `framework.json` | `runtime.platform`（用户选的 IDE）、`upgrade.state`（升级状态） |
| `PROJECT-STATE.md` | 整个文件（项目运行手册，用户自行维护） |

其余字段（`constants` / `features` / `migration_checks` / `upgrade.source` / `version`）每次都用最新 scaffold 覆盖。

完整升级语义见 [`upgrade.md`](./upgrade.md)。

---

## Deploy 幂等与孤儿清理

多次 `cataforge deploy` 是幂等的，且会自动清理上次部署留下的孤儿：

- `commands/*.md`：源目录里删除 / 重命名的命令会被 prune
- Claude Code（扁平布局）：`.claude/agents/*.md` 中源 `agents/` 已移除的 agent 文件会被 prune
- Cursor / OpenCode（嵌套布局）：`.cursor/agents/<name>/` 或 `.opencode/agents/<name>/` 中源 `agents/` 删除的子目录会被 prune（仅删含 `AGENT.md` 的目录，不伤 IDE 原生或用户自建 agent）；子目录内非 `AGENT.md` 的历史文件也会被 prune

无需手动 `git clean -fd .claude/` 再重部署。

---

## 参考

- 流水线总览：[`manual-verification.md`](./manual-verification.md)
- 分平台 6 步操作：[`verify-per-platform.md`](./verify-per-platform.md)
- 标准测试用例：[`verify-cases.md`](./verify-cases.md)
- CLI 参考：[`../reference/cli.md`](../reference/cli.md)
