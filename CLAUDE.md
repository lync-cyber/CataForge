# CataForge

## 项目信息

- 技术栈: {框架/语言/工具}
- 开发框架: CataForge
- 运行时: claude-code (其他运行时暂不支持)
- 框架版本: {从 pyproject.toml [project].version 读取}

## 执行环境 (Bootstrap 时由 setup.py --emit-env-block 填入)

<!-- 本节在 Bootstrap 步骤中生成。每次会话都会作为项目指令加载，
     权重高于 hook 注入的 additionalContext。项目生命周期内保持稳定。 -->
{执行环境检测结果 — 未填入时 orchestrator 应在 Bootstrap 时调用:
 python .claude/scripts/setup.py --emit-env-block}

## 项目状态 (orchestrator专属写入区，其他Agent禁止修改)

- 当前阶段: {requirements|architecture|ui_design|dev_planning|development|testing|deployment|completed}
- 上次完成: {agent目录名} — {简要描述完成的工作}
- 下一步行动: {具体的下一步}
- 已完成阶段: []
- 当前Sprint: — (DEV阶段由orchestrator在Sprint推进时更新)
- 文档状态:
  - prd: 未开始
  - arch: 未开始
  - ui-spec: 未开始
  - dev-plan: 未开始
  - test-report: 未开始
  - deploy-spec: 未开始
  <!-- changelog 由 devops 产出但不纳入门禁追踪 -->
- Learnings Registry: (首次 retrospective 后填充)

## 文档导航

- 导航索引: docs/NAV-INDEX.md (所有Agent优先查阅此文件)
- 通用规则: .claude/rules/COMMON-RULES.md (所有Agent共享的行为规则)
- 子代理协议: .claude/rules/SUB-AGENT-PROTOCOLS.md (revision/continuation/amendment流程)
- 编排协议: .claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md (orchestrator专属)
- 状态码Schema: .claude/schemas/agent-result.schema.json (agent-result 格式权威定义)
- 加载原则: 按任务需要通过NAV-INDEX定位并加载相关章节

## 全局约定

- 命名: {规范}
- Commit: {格式}
- 分支: {策略}
- 设计工具: none
  <!-- 可选值: none | penpot。设为 penpot 时启用 Penpot MCP 集成，需本地运行 Penpot + MCP Plugin -->
- 人工审查检查点: [pre_dev, pre_deploy]
  <!-- 可选值: phase_transition | pre_dev | pre_deploy | post_sprint | none。详见 COMMON-RULES §MANUAL_REVIEW_CHECKPOINTS -->
- 文档类型命名: 统一用小写 kebab-case（prd、arch、dev-plan、test-report、ui-spec、deploy-spec…），包括人类可读文本、工具参数（template_id/doc_type）和产出文件名（如 arch-{project}-{ver}.md）

## 效率原则 (全局遵循)

- 按需加载: 先查NAV-INDEX，仅加载任务相关章节
- 最小传递: Agent间传递doc_id#section引用，非全文
- 不确定时调研: 调用research skill，不猜测
- 选择题优先: 需要用户输入时优先提供选项
- 长文拆分: 文档超500行时按doc-gen拆分策略分卷

## 框架执行机制

- Agent编排: orchestrator通过agent-dispatch skill激活子代理
- DEV阶段特殊处理: Phase 5由orchestrator直接通过tdd-engine skill编排RED/GREEN/REFACTOR三个子代理，每个子代理拥有独立上下文
- Skill调用: Agent按SKILL.md中的步骤式指令执行工作流
- 状态持久化: 所有状态写入CLAUDE.md和docs/目录
- 子代理通信: 通过文件系统(docs/和src/)传递产出物路径
- 运行时: 仅 claude-code（agent-dispatch 通过 Agent tool + subagent_type 调度子代理）
- **写权限规则**: CLAUDE.md由orchestrator独占写入；其他Agent只写各自在docs/或src/下的产出文件，任务执行进度通过doc-gen更新dev-plan文档

## 框架元信息

- 语言定位: 中文框架（所有提示词、文档模板、用户交互均为中文；代码/变量/CLI参数使用英文）
- model:inherit 说明: 所有 AGENT.md 中 `model: inherit` 表示继承父会话（即 orchestrator 或用户会话）的模型设置。如需为特定 Agent 指定模型，可在 AGENT.md frontmatter 中设置 `model: <model-id>`
- 执行模式: standard
  <!-- 可选值: standard | agile-lite | agile-prototype。默认 standard；agile-* 仅适用于轻量项目/原型/PoC。矩阵见 COMMON-RULES §执行模式矩阵。模式切换由 orchestrator §Mode Routing Protocol 路由 -->
- 阶段配置: 以下阶段可在 Bootstrap 时标记为 N/A 以跳过:
  - ui_design: 后端/CLI/API-only 项目可跳过（默认行为）
  - testing: 原型/PoC 项目可跳过
  - deployment: 库/SDK 项目可跳过
  <!-- orchestrator 在 Bootstrap Step 1 收集项目信息时，向用户确认可跳过的阶段 -->
