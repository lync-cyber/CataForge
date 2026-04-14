---
name: agent-dispatch
description: "子代理调度 — 将Agent激活指令翻译为运行时具体操作。"
argument-hint: "<agent_id: 目录名如architect> <task: 任务描述>"
suggested-tools: file_read, file_glob, file_grep, shell_exec, agent_dispatch
depends: []
disable-model-invocation: false
user-invocable: false
---

# 子代理调度 (agent-dispatch)

## 能力边界
- 能做: 将"激活Agent X执行任务Y"指令翻译为当前运行时环境的具体操作
- 不做: 决定激活哪个Agent(由orchestrator决定)、决定任务内容(由上游Agent决定)

## 调度输入
调用方(orchestrator)提供:
- **agent_id**: 目标Agent目录名 (如 "architect", "reviewer")
- **task**: 任务描述
- **task_type**: new_creation | revision | continuation | retrospective | skill-improvement | apply-learnings | amendment
- **input_docs**: 输入文档路径列表
- **expected_output**: 期望产出类型
- 仅revision: REVIEW报告路径
- 仅continuation: 用户回答、中间产出路径、恢复指引
- 仅retrospective: input_docs 为 [docs/reviews/doc/, docs/reviews/code/, docs/reviews/sprint/, docs/reviews/retro/, docs/reviews/CORRECTIONS-LOG.md]，expected_output 为 RETRO 报告
- 仅skill-improvement: input_docs 为满足内化条件的 EXP 条目列表，expected_output 为 SKILL-IMPROVE 报告
- 仅apply-learnings: input_docs 为 RETRO 报告路径 + 用户审批的 EXP 编号列表，expected_output 为 learnings 文件路径列表
- 仅amendment: change-analysis 结果(XML格式)、用户变更描述

## Agent-Skill 依赖映射
> **单一事实来源**: 各 AGENT.md 的 `skills:` 字段（由 subagent_type 自动加载）。
> 本文件不维护映射副本。查询当前映射请运行:
> ```
> grep -h 'skills:' -A 20 .cataforge/agents/*/AGENT.md
> ```

## 平台调度实现
当前运行时平台由 `.cataforge/platforms/{platform_id}/profile.yaml` 声明。
调度工具名和参数由 profile.yaml 的 `dispatch` 段定义。

完整 prompt 模板见: `.cataforge/skills/agent-dispatch/templates/dispatch-prompt.md`（含 OVERRIDE 标记点）。
平台 override 见: `.cataforge/platforms/{platform_id}/overrides/dispatch-prompt.md`。

运行时工具层（`.cataforge/runtime/`）提供:
- `profile_loader.py`: 加载平台 profile 和 tool_map
- `template_renderer.py`: 基础模板 + override 合并
- `frontmatter_translator.py`: AGENT.md 能力标识符翻译
- `result_parser.py`: 4 级容错解析器

> 修改 prompt 模板影响所有通过 agent-dispatch 调度的 Agent，请谨慎变更并做 diff review。
> TDD 子代理由 tdd-engine 直接调度，仅传入任务信息，通用约束和返回格式依赖 AGENT.md 自动加载，无需同步。

## 返回值解析与容错
orchestrator 收到子代理返回后，按以下优先级解析:

1. **正常解析**: 提取 `<agent-result>` 标签内容，获取 status/outputs/summary
2. **标签缺失兜底**: 如果返回文本中不含 `<agent-result>`:
   - 使用 `Glob docs/{doc_type}/` 检查是否有新文件产出
   - 有新文件 → 推断为 completed，outputs 为新文件路径列表
   - 无新文件 → 标记为 blocked，记录原因"子代理未返回结构化结果"
3. **标签不完整兜底**: 如果 `<agent-result>` 缺少必填字段(status/outputs):
   - 缺 status → 默认为 completed (如果有 outputs)
   - 缺 outputs → 使用 Glob 扫描 docs/ 推断产出
4. **maxTurns 截断恢复**: 如果子代理明显被截断(返回文本不含结束标签):
   - 通过 `git status docs/` 检查是否有自本次调度后新增或修改的文件（untracked 或 modified）
   - 有新增/修改文件 → 检查文件内容是否含非空章节（至少一个 ## 标题下有实际内容），有则以 continuation 模式重新调度同一Agent
   - 无新增/修改文件或文件仅含空骨架 → 标记 blocked 并请求人工介入

5. **写入范围校验（通用）**: 子代理返回后，orchestrator 通过 `git diff --name-only` 检查本次调度期间修改的文件:
   - 读取目标 Agent 的 AGENT.md frontmatter 中 `allowed_paths` 字段
   - `allowed_paths` 为空数组 `[]` 时跳过校验（orchestrator 等无限制 Agent）
   - 所有修改文件均在 allowed_paths 列表的目录下 → 正常
   - 存在 allowed_paths 以外的修改文件 → 使用 `git checkout -- {违规文件}` 回滚，在 summary 中标注"Agent 写入违规已回滚"，记录违规文件路径

Python 实现: `.cataforge/runtime/result_parser.py`

## 注意事项
- 每个Phase Agent作为独立子代理运行，拥有自己的上下文窗口
- 子代理无法直接访问调用方的上下文，所有必要信息通过prompt传入
- **子代理无法使用调度工具** — TDD子代理由orchestrator直接通过tdd-engine skill启动
- subagent_type 使子代理自动加载 AGENT.md 中的角色定义、工具权限和约束

## 运行时支持
支持的运行时平台由 `.cataforge/platforms/` 下的 profile.yaml 声明。
当前已配置: claude-code, cursor, codex, opencode。

## 效率策略
- 调度层薄而透明: 仅负责翻译，不增加额外逻辑
- subagent_type 自动加载 AGENT.md，节省子代理文件读取 turn
- prompt 模板外置于 templates/dispatch-prompt.md，便于独立 diff/review
- 状态通过文件系统传递，避免上下文膨胀
