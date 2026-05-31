### Fixed

- **`detect_review_flag` 降级根因更正** —— `hooks.yaml` 与 `docs/reference/platform-capability-matrix.md` 原把 codex 降级归因为"依赖 schema v2 `matcher_agent_id`，v1-only 平台无法约束"，与运行时实现（`matcher_agent_id` 由 Python 在 hook 内强制，与平台 schema 版本无关）相悖；更正为真实根因"依赖 agent_dispatch 的 PostToolUse 匹配，无 agent matcher 的平台不触发"。
- **`penpot-sync` 默认 `bidirectional` 与 Anti-Pattern 自相矛盾** —— Step 4 澄清默认双向为"以 ui-spec 为唯一权威源的两次受控单向写出，不反向读回"，Anti-Pattern 改为针对"无权威源的双向自动回写覆盖循环"。
- **`arc-design` Anti-Pattern 引用不存在的章节** —— 由"§6 部署运行时"更正为真实存在的"§5.4 配置管理"。
- **`framework-review` 白名单重复项 / category 枚举缺漏** —— 去除 B2-α 白名单中重复的 `context`；§问题格式 category 枚举补上下文已使用的 `dead-code`。

### Changed

- **conditional_release 的归属与判定条件归位** —— `COMMON-RULES.md` §三态判定逻辑保持公共三态（reviewer 适用），仅加一句指针说明 qa-engineer 扩展第四态；conditional_release 的判定条件（"唯一未决项是因环境/CI 不可达的非缺陷阻塞时选用"）落到 `qa-engineer/AGENT.md`；§统一状态码 点明 conditional_release 是 verdict 而非 status 枚举。
- **多个 SKILL 补触发场景句** —— `req-analysis` / `start-orchestrator` / `tech-eval` / `agent-dispatch` / `task-decomp` / `testing` / `ui-design` 的 description 补"当…时使用"触发句，提升 LLM 自动调用准确率；`start-orchestrator` 能力边界由同义反复改为实际动作清单。
- **Anti-Patterns 格式统一为对比式** —— `framework-feedback` 与 `reviewer/AGENT.md` 的若干条由陈述句改为"禁止/避免 + 对比"格式。
- **debug skill 与语言解耦** —— Python/Windows 特定问题模式表下沉到新增的 `docs/reference/debug-patterns.md`，skill 主体改链接引用并改用语言无关表述。
- **`debugger` allowed_paths 收窄** —— 移除 `.cataforge/skills/`（prompt 文档，非可调试脚本），保留 dogfood 所需的 `.cataforge/scripts/` 与 `.cataforge/hooks/`。
- **元资产整洁度精简** —— `orchestrator/AGENT.md` 去除版本锚定表述；`workflow-framework-generator` 折叠领域模式预览表与扩展机制清单为指针/单行；`tdd-engine` 将重复的 dispatch 引导句提取为 §TDD 子代理共享约束 单一声明（行为中性）。
