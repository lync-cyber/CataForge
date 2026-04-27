<!-- 变更原因：从 manual-verification.md 拆出 §4 标准测试用例；纯 Reference 形态，便于在 Verification Report 里直接勾 -->
# 手动验证 · 标准测试用例

> 按优先级执行；前 6 项为必过。✅ 表示建议保留勾选用于 Verification Report。

| # | Case | 命令 | 判定 |
|---|------|------|-----|
| 1 | 环境健康 | `cataforge doctor` | `Diagnostics complete.` 且无 `MISSING` |
| 2 | Agent 发现 | `cataforge agent list` | 条目 > 0 |
| 3 | Skill 发现 | `cataforge skill list` | 条目 > 0 且含 `code-review` |
| 4 | Hook 加载 | `cataforge hook list` | 至少含 `PreToolUse` + `PostToolUse` |
| 5 | Cursor 干运行 | `cataforge deploy --dry-run --platform cursor` | 命中 `hooks.json` + `.mdc` |
| 6 | CodeX 干运行 | `cataforge deploy --dry-run --platform codex` | 命中 `AGENTS.md` + `config.toml` |
| 7 | OpenCode 降级 | `cataforge deploy --dry-run --platform opencode` | 含 `SKIP:` + `rules_injection` |
| 8 | 自动化回归 | `pytest -q` | 退出码 0，全部用例通过 |
| 9 | MCP 生命周期 | 见 [`verify-topics.md`](./verify-topics.md) §MCP | `list` / `start` / `stop` 均成功 |
| 10 | IDE 内生效 | 见 [`verify-per-platform.md`](./verify-per-platform.md) Step 4 | 至少一个 IDE 观测到 Agent + Rules + MCP |

## 失败定位

任一 Case 不通过，按下表查归属文档：

| 症状 | 去这里 |
|------|------|
| 环境 / 安装 / 乱码 | [`../getting-started/troubleshooting.md`](../getting-started/troubleshooting.md) |
| 部署后 IDE 内看不到产物 | [`verify-per-platform.md`](./verify-per-platform.md) 对应平台 Step 4 |
| Hook 不触发 | [`verify-topics.md`](./verify-topics.md) §Hook 生效观察 |
| MCP 启不动 | [`verify-topics.md`](./verify-topics.md) §MCP 生命周期 |
| 升级后异常 | [`upgrade.md`](./upgrade.md) |

## 参考

- 流水线总览：[`manual-verification.md`](./manual-verification.md)
- 分平台 6 步操作：[`verify-per-platform.md`](./verify-per-platform.md)
- 专题验证：[`verify-topics.md`](./verify-topics.md)
