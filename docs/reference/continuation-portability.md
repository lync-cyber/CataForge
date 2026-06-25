# Continuation Portability — 子代理续接的跨平台现实

CataForge 的 continuation（`task_type=continuation` 与 maxTurns 截断恢复）一律 **file-based 重派发**：每次 dispatch 是独立上下文窗口，恢复靠从中间产出文件 reload，不依赖运行时平台「带上下文续接已派发子代理」的原生原语。原因是该能力在四个目标平台两两不同，不能作为可移植基线。

## 「子代理续接」与「会话恢复」是两套机制

- 子代理续接：用已派发子代理的句柄/ID 再次发消息、保留其上下文继续执行（区别于重新 spawn 一个上下文清空的子代理）。
- 会话恢复：恢复主会话（resume / --continue）。各平台普遍支持，但与子代理续接不可混用。

## 四平台「子代理续接」对照

| 平台 | 子代理续接 | 原语 | 状态 |
|------|-----------|------|------|
| claude-code | 门禁/实验 | `SendMessage(to: agentId)` | 文档化但需 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`，默认不可用 |
| codex | 原生支持 | `/agent` 交互 steer + MCP `codex-reply`(threadId) | 官方 |
| cursor | 原生支持 | `Resume agent <ID>` | 官方，完整保留上下文 |
| opencode | 未向用户暴露 | task_id（仅代码内） | 开放 feature request |

信源：

- claude-code: https://code.claude.com/docs/en/tools-reference.md （门禁证据 https://github.com/anthropics/claude-code/issues/38183）
- codex: https://developers.openai.com/codex/subagents
- cursor: https://cursor.com/docs/subagents
- opencode: https://github.com/sst/opencode/issues/24756

## 约束

dispatch / continuation 协议禁止依赖上述任何平台原语，续接只走 file-based 重派发。规则落点：[agent-dispatch SKILL.md](../../.cataforge/skills/agent-dispatch/SKILL.md) §注意事项、[SUB-AGENT-PROTOCOLS.md](../../.cataforge/rules/SUB-AGENT-PROTOCOLS.md) §task_type=continuation。
