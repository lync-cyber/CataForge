# CataForge

## 项目信息

- 技术栈: {框架/语言/工具}
- 运行时: {platform}
- 框架版本: pyproject.toml `[project].version`（SemVer: MAJOR=不兼容变更, MINOR=新功能, PATCH=修复）
- 语言定位: 中文框架（提示词/文档/交互用中文；代码/变量/CLI参数用英文）
- 执行模式: standard
  <!-- 可选值: standard | agile-lite | agile-prototype。矩阵见 COMMON-RULES §执行模式矩阵。模式切换由 orchestrator §Mode Routing Protocol 路由 -->
- 阶段配置: 以下阶段可在 Bootstrap 时标记为 N/A 以跳过:
  - ui_design: 后端/CLI/API-only 项目可跳过（默认行为）
  - testing: 原型/PoC 项目可跳过
  - deployment: 库/SDK 项目可跳过
  <!-- orchestrator 在 Bootstrap Step 1 收集项目信息时，向用户确认可跳过的阶段 -->
- model 继承: AGENT.md 中 `model: inherit` 继承父会话模型；可用 `model: <model-id>` 覆盖

## 执行环境 (Bootstrap 时由 `cataforge setup --emit-env-block` 填入)

<!-- 本节在 Bootstrap 步骤中生成。每次会话都会作为项目指令加载，
     权重高于 hook 注入的 additionalContext。项目生命周期内保持稳定。 -->
{执行环境检测结果 — 未填入时 orchestrator 应在 Bootstrap 时调用:
 cataforge setup --emit-env-block}

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

- 导航索引: `docs/.doc-index.json`（机器索引，所有 Agent 通过 `cataforge docs load` 查询；缺失时运行 `cataforge docs index` 重建）
- 通用规则: .cataforge/rules/COMMON-RULES.md
- 子代理协议: .cataforge/rules/SUB-AGENT-PROTOCOLS.md
- 编排协议: .cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md (orchestrator专属)
- 状态码Schema: .cataforge/schemas/agent-result.schema.json
- 加载原则: 按任务需要通过 `cataforge docs load` 加载相关章节，不全量加载

## 全局约定

- 命名: {规范}
- Commit: {格式}
- 分支: {策略}
- 设计工具: none
  <!-- 可选值: none | penpot。设为 penpot 时启用 Penpot MCP 集成 -->
- 人工审查检查点: [pre_dev, pre_deploy]
  <!-- 详见 COMMON-RULES §MANUAL_REVIEW_CHECKPOINTS -->
- 文档类型命名: 小写 kebab-case（prd、arch、dev-plan、test-report、ui-spec、deploy-spec…），含工具参数和产出文件名
- 效率原则:
  - 最小传递: Agent间传递doc_id#section引用，非全文
  - 不确定时调研: 调用research skill，不猜测
  - 选择题优先: 需要用户输入时优先提供选项
  - 长文拆分: 文档超 `DOC_SPLIT_THRESHOLD_LINES` 行时按doc-gen拆分策略分卷

## 框架机制

- Agent编排: orchestrator 通过 agent-dispatch skill 激活子代理
- DEV阶段: orchestrator 通过 tdd-engine skill 编排 RED/GREEN/REFACTOR 三个子代理（独立上下文）
- Skill调用: Agent按SKILL.md步骤式指令执行工作流
- 状态持久化: PROJECT-STATE.md + docs/ 目录
- 子代理通信: 通过文件系统(docs/和src/)传递产出物路径
- 运行时: 由 framework.json runtime.platform 决定（deploy 自动适配）
- **写权限**: PROJECT-STATE.md 由 orchestrator 独占写入；其他Agent只写 docs/ 或 src/ 下的产出文件
- 统一配置 `.cataforge/framework.json`:
  - `upgrade.source` — 远程升级源配置。升级时保留用户已配置值，仅补充新字段
  - `upgrade.state` — 本地升级状态。升级时始终保留
  - `features` — 功能注册表。升级时全量覆盖
  - `migration_checks` — 迁移检查声明。升级时全量覆盖
