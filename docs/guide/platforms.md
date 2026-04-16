# 平台适配指南

> 本文说明 CataForge 在 Claude Code / Cursor / CodeX / OpenCode 四个 IDE 上的原生支持情况、产物落盘位置与最小配置。
>
> 原理层面（`PlatformAdapter` 抽象、翻译关系、降级策略）请看 [`../architecture/platform-adaptation.md`](../architecture/platform-adaptation.md)。

<p align="center">
  <img src="../assets/artifact-map.svg" alt="CataForge 四平台部署产物对照图" width="100%">
</p>

## 概览

| 平台 | Agent | Hook | MCP | 指令文件 |
|------|:-----:|:----:|:---:|---------|
| Claude Code | ✅ 原生 | ✅ 原生 | ✅ 原生 | `CLAUDE.md` |
| Cursor | ✅ 原生 | ✅ 原生 | ✅ 原生 | `AGENTS.md` + `.mdc` |
| CodeX | 🟡 中等 | 🟡 仅 Bash | ✅ 原生 | `AGENTS.md` |
| OpenCode | 🟡 规则注入 | 🔻 降级 | ✅ 原生 | `opencode.json` + `AGENTS.md` |

- ✅ 原生映射；🟡 部分支持 / 能力受限；🔻 自动降级。

---

## Claude Code

- **原生支持**：Agent、Hook、MCP 均可原生映射。
- **关键路径**：`.claude/agents/`、`CLAUDE.md`、`.claude/settings.json`、`.mcp.json`。
- **最小配置**（`.cataforge/framework.json` 片段）：

```json
{
  "runtime": {
    "platform": "claude-code"
  }
}
```

## Cursor

- **原生支持**：大部分原生支持（`AskUserQuestion` 与 `Notification` 会降级）。
- **关键路径**：`.cursor/agents/`、`.cursor/hooks.json`、`.cursor/rules/*.mdc`、`.cursor/mcp.json`、`AGENTS.md`。
- **适配点**：
  - 规则额外生成 Cursor 原生消费的 MDC 格式文件。
  - **默认不触及 `.claude/` 目录**。仅当 `.cataforge/platforms/cursor/profile.yaml` 设置 `rules.cross_platform_mirror: true` 时，才会在 `.claude/rules` 创建 Markdown 镜像，供 "Cursor + Claude Code 双栖" 场景共享 prompt。
- **最小配置**：

```json
{
  "runtime": {
    "platform": "cursor"
  }
}
```

## CodeX

- **原生支持**：中等，以 `AGENTS.md` + `.codex/config.toml` 为主。
- **关键路径**：`AGENTS.md`、`.codex/agents/*.toml`、`.codex/hooks.json`、`.codex/config.toml`。
- **适配点**：
  - 指令文件按 Codex 原生体系输出为 `AGENTS.md`。
  - MCP 写入 `.codex/config.toml` 的 `[mcp_servers.<id>]`。
  - Hooks 仅支持 `Bash` matcher，其它事件降级。
- **最小配置**：

```json
{
  "runtime": {
    "platform": "codex"
  }
}
```

## OpenCode

- **原生支持**：中等，以 `.opencode` 目录 + `opencode.json` 为主。
- **关键路径**：`.opencode/agents/*.md`、`opencode.json`、`AGENTS.md`。
- **适配点**：
  - Hook 原生不可用，自动注入为 `rules_injection`（规则提示中嵌入检查指令）。
  - 若需原生 hook，需自行包装为 `.opencode/plugins/*.ts`。
  - `.claude` 路径仅作兼容后备。
- **最小配置**：

```json
{
  "runtime": {
    "platform": "opencode"
  }
}
```

---

## 跨平台目录隔离

每个平台部署只生成**自己命名空间**下的产物（`.claude/` / `.cursor/` / `.codex/` / `.opencode/`），互不干扰。

- Cursor 部署**默认不会**触及 `.claude/`。
- 干运行（`deploy --check`）会明示 `SKIP: .claude/rules Markdown mirror`，避免用户误以为 Cursor 部署 "莫名碰了 Claude 目录"。

---

## 切换平台

```bash
cataforge setup --platform <id>     # 切换运行时平台
cataforge deploy --platform <id>    # 投放到新平台（--check 可干运行）
```

`.cataforge/` 规范不变，仅重写目标平台的产物。

---

## 参考

- 端到端在 4 个 IDE 内真实跑通：[`manual-verification.md`](./manual-verification.md)
- 适配器翻译关系与降级机制：[`../architecture/platform-adaptation.md`](../architecture/platform-adaptation.md)
- 平台 profile 配置文件：[`../reference/configuration.md`](../reference/configuration.md)
