# 快速开始

> 目标：**3 条命令**跑通一个 Cursor 工作流部署的干运行。

## 前置

已完成 [`installation.md`](./installation.md) 中的任一安装方式，`cataforge --version` 可用。

## 最短路径（3 条命令）

```bash
# 1. 健康诊断（检查框架目录、依赖、平台 profile）
cataforge doctor

# 2. 初始化：设定目标平台为 Cursor（可选 claude-code / cursor / codex / opencode）
cataforge setup --platform cursor

# 3. 干运行部署：查看会写入哪些产物，不实际写盘
cataforge deploy --dry-run --platform cursor
```

## 成功标志

| 命令 | 末行关键字 |
|------|-----------|
| `cataforge doctor` | `Diagnostics complete.` |
| `cataforge setup --platform cursor` | `Setup complete. Run cataforge deploy ...` |
| `cataforge deploy --dry-run --platform cursor` | `Deploy complete.` |

## 真正写入 IDE 产物

干运行确认无误后，去掉 `--dry-run` 即可真部署：

```bash
cataforge deploy --platform cursor
```

产物落盘位置（Cursor 示例）：

```text
AGENTS.md
.cursor/agents/*/AGENT.md
.cursor/hooks.json
.cursor/rules/*.mdc
.cursor/mcp.json              # 若声明了 MCP
```

> 所有部署产物默认被 `.gitignore` 排除（有意为之）。用 `git status -u` 审阅完整清单。

## 切换平台

`.cataforge/` 规范同一份，切换目标平台只需重设：

```bash
cataforge setup --platform claude-code   # 或 codex / opencode
cataforge deploy --platform claude-code
```

## 从源码直跑（不安装）

```bash
python -m cataforge doctor
python -m cataforge setup --platform cursor
python -m cataforge deploy --dry-run --platform cursor
```

## 下一步

- 四平台端到端完整验证：[`../guide/manual-verification.md`](../guide/manual-verification.md)
- 平台适配细节（原生支持 / 降级策略）：[`../guide/platforms.md`](../guide/platforms.md)
- 看懂 Agent / Skill 做了什么：[`../reference/agents-and-skills.md`](../reference/agents-and-skills.md)
