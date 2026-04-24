# 快速开始

> 目标：**3 条命令**跑通一个 Cursor 工作流部署的干运行。

## 前置

已完成 [`installation.md`](./installation.md) 中的任一安装方式，`cataforge --version` 可用。

## 整体流程

```mermaid
flowchart LR
    A[cataforge doctor<br/>检查环境] --> B[cataforge setup<br/>--platform X<br/>写入 .cataforge/]
    B --> C[cataforge deploy<br/>--dry-run<br/>预览 IDE 产物]
    C --> D[cataforge deploy<br/>真部署]
    D --> E[(IDE 可用：<br/>CLAUDE.md / .claude/<br/>.cursor/ / AGENTS.md)]

    classDef step fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    classDef dry fill:#fff8e1,stroke:#f9a825,color:#6d4c00
    classDef final fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    class A,B step
    class C dry
    class D,E final
```

- **setup** 只写 `.cataforge/`（规范源 + `framework.json`），不碰 IDE 目录。
- **deploy** 把 `.cataforge/` 翻译成当前 IDE 认识的产物。`--dry-run` 仅列清单。
- 随时可切平台——改 `--platform` 重跑 deploy 即可。

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

根据你的意图选路径：

| 你想 … | 去 |
|---------|----|
| **在 Claude Code / Cursor 真实跑一遍** | [`../guide/platforms.md`](../guide/platforms.md) — 各 IDE 的原生支持与降级策略 |
| **跑 4 平台端到端验证** | [`../guide/manual-verification.md`](../guide/manual-verification.md) — 5 步交叉验证 |
| **把 CataForge 升到新版本** | [`../guide/upgrade.md`](../guide/upgrade.md) — 升级流程与文件保留规则 |
| **定制 Agent / Skill** | [`../reference/agents-and-skills.md`](../reference/agents-and-skills.md) — 用户可以做什么 vs. 不能动什么 |
| **看 CataForge 怎么工作的** | [`../architecture/overview.md`](../architecture/overview.md) — 架构分层、翻译层设计 |
