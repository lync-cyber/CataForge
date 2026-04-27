<!-- 变更原因：增加成功 / 失败两条路径的具体输出对照；删除"一键"营销词；保留 mermaid 图改为更精炼的状态表（图与文字重复时二选一） -->
# 快速开始

> 目标：5 分钟内在你的本机和你选定的 IDE 里跑出第一个 CataForge 部署。

## 你需要先有

- 已完成 [安装](./installation.md)，`cataforge --version` 可执行
- 你想用的 IDE 之一：Claude Code、Cursor、CodeX、OpenCode

## 一条命令跑通

```bash
cd <你的项目根目录>
cataforge bootstrap --platform cursor    # 替换为 claude-code / codex / opencode
```

`bootstrap` 会按现状决定每步是否要跑：

| 步骤 | 判断依据 | 跳过条件 |
|------|---------|---------|
| `setup` | `.cataforge/` 是否存在 | 已存在则跳过 |
| `upgrade apply` | 包版本 vs scaffold 版本 | 一致则跳过 |
| `deploy` | `.deploy-state` 平台戳记 | 与当前平台一致则跳过 |
| `doctor` | 始终跑 | 不跳过 |

再次运行时多数步骤会跳过，整个命令幂等。

## 期望输出

成功（终端最后一行）：

```text
Diagnostics complete.
```

干运行预览（命令加 `--dry-run`）：

```text
Plan (dry-run):
  • setup    run   — no .cataforge/ at <path> — fresh scaffold
  ○ upgrade  skip  — fresh scaffold already current
  • deploy   run   — fresh install — initial deploy required
  • doctor   run   — verification gate
```

<!-- 变更原因：补失败路径示例，原文档只写 happy path -->

失败（典型）：

```text
Error: project root not found.
Hint: cd into a directory that has a .cataforge/ folder, or run with --project-dir.
```

按 stderr 提示的 `Hint:` 操作即可。仍卡住时跳到 [故障排查](./troubleshooting.md)。

## 看部署落了哪些产物

以 Cursor 为例：

```bash
git status -u    # .gitignore 默认忽略产物，需要 -u 才能看到
```

应当出现：

```text
AGENTS.md
.cursor/agents/*/AGENT.md
.cursor/hooks.json
.cursor/rules/*.mdc
.cursor/mcp.json              # 当 .cataforge/mcp/ 非空时
```

四个平台的完整产物路径见 [速查卡](../reference/quick-reference.md) §产物落盘路径。

## 切换到另一个平台

`bootstrap` 不会隐式改写 `runtime.platform`，避免误锁错平台。要切换时显式走 `setup`：

```bash
cataforge setup --platform claude-code --show-diff   # 先看会改 framework.json 的哪个字段
cataforge bootstrap                                   # 检测到平台漂移会重新 deploy
```

## 不安装，从源码直跑

```bash
git clone https://github.com/lync-cyber/CataForge.git && cd CataForge
python -m cataforge bootstrap --platform cursor --dry-run
```

## 下一步

| 你想 …… | 去 |
|---------|----|
| 在 IDE 内跑第一个 Agent 对话 | [`../guide/manual-verification.md`](../guide/manual-verification.md) |
| 理解 4 个 IDE 之间的能力差异 | [`../guide/platforms.md`](../guide/platforms.md) |
| 升级到下一版本或回滚 | [`../guide/upgrade.md`](../guide/upgrade.md) |
| 自定义 Agent / Skill | [`../reference/agents-and-skills.md`](../reference/agents-and-skills.md) |
| 看内部如何工作 | [`../architecture/overview.md`](../architecture/overview.md) |
