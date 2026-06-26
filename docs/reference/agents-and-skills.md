# Agent 与 Skill 清单

本文档列出 CataForge 框架内置的所有 Agent 和 Skill，包括角色说明、工具权限、关联技能等信息。

> 源定义文件位于 `.cataforge/agents/` 和 `.cataforge/skills/` 目录。
>
> **适用版本**：v0.4.x。计数 13 Agent + 28 Skill 由 [`scripts/checks/check_skill_count.py`](../../scripts/checks/check_skill_count.py) 守护（动态计算 `.cataforge/skills/` 子目录数，文档断言不一致即 FAIL）。
>
> **平台差异**：Agent 通过 `tools.allow` 声明的 capability 在各平台的原生工具映射见 [platform-capability-matrix.md](platform-capability-matrix.md)；`null` 映射的 capability 在 deploy 时被过滤并发 WARN。

## 目录

- [工具权限语法](#工具权限语法) — `allow` 与 `deny` 如何协同
- [Agent 清单（13 个）](#agent-清单13-个) — 总览表 + 详细说明（默认折叠）
- [Skill 清单（26 个）](#skill-清单26-个) — 总览表 + 按类别折叠
- [Agent-Skill 关联矩阵](#agent-skill-关联矩阵) — 默认启用 / 条件启用 / 独立 Skill

---

## 工具权限语法

每个 `AGENT.md` frontmatter 用 `tools:` 声明工具权限：

```yaml
tools:
  allow: [file_read, file_write, file_edit, file_glob, file_grep, user_question]
  deny:  [agent_dispatch, shell_exec]
```

优先级规则：

- `allow:` 列表 — 仅允许这些工具。若留空或省略 `allow` 键，默认允许全部工具。
- `deny:` 列表 — 在 allow 之外再减去这些工具。**deny 优先级高于 allow**（同名时 deny 生效）。
- 两者都省略 — 允许全部工具（不推荐，仅 `orchestrator` 这样需要无限权限的 Agent 适用）。

下面每个 Agent 的"允许工具"/"禁用工具"两行即对应 `allow:` / `deny:` 字段。

---

## Agent 清单（13 个）

### 总览

| # | Agent | 中文角色 | 职责概要 | MaxTurns |
|---|-------|---------|---------|----------|
| 1 | orchestrator | 主编排智能体 | 协调整个 SDLC 生命周期 | 200 |
| 2 | product-manager | 产品经理 | 需求分析与 PRD 撰写 | 60 |
| 3 | architect | 架构师 | 架构设计与技术选型 | 60 |
| 4 | ui-designer | UI 设计师 | 界面设计与交互规范 | 60 |
| 5 | tech-lead | 技术主管 | 任务分解与开发计划 | 60 |
| 6 | test-writer | TDD RED 阶段 | 编写失败测试用例 | 50 |
| 7 | implementer | TDD GREEN 阶段 | 编写最小实现使测试通过 | 50 |
| 8 | refactorer | TDD REFACTOR 阶段 | 优化代码质量，保持测试通过 | 50 |
| 9 | reviewer | 评审员 | 跨阶段质量审查（文档与代码） | 50 |
| 10 | qa-engineer | 测试工程师 | 测试策略与集成/E2E 测试 | 50 |
| 11 | devops | 运维工程师 | 构建、部署与发布配置 | 50 |
| 12 | debugger | 调试工程师 | 运行时错误诊断与最小修复 | 40 |
| 13 | reflector | 反思者 | 提取跨项目经验教训 | 30 |

### 详细说明

> 点击展开查看各 Agent 的职责、工具权限、写入路径等详细定义。

<details>
<summary><b>1. orchestrator</b> — 主编排智能体（协调整个 SDLC）</summary>

- **职责**：协调整个软件开发生命周期，负责项目引导（Bootstrap）、阶段路由、手动审查检查点、中断恢复协议、TDD 编排。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, agent_dispatch, user_question
- **写入路径**：无限制
- **关联 Skill**：agent-dispatch, context, tdd-engine, change-guard, framework-feedback
- **特殊协议**：拥有专属编排协议（ORCHESTRATOR-PROTOCOLS.md），管理阶段转换、修订流程、Sprint 回顾触发等。

</details>

<details>
<summary><b>2. product-manager</b> — 产品经理（需求分析 / PRD）</summary>

- **职责**：需求分析、用户故事编写、PRD 文档生成。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, web_search, web_fetch, user_question
- **禁用工具（deny）**：shell_exec, agent_dispatch
- **写入路径**：docs/prd/, docs/research/
- **关联 Skill**：req-analysis, context, research

</details>

<details>
<summary><b>3. architect</b> — 架构师（架构设计 / 技术选型）</summary>

- **职责**：架构设计、技术选型、模块划分、接口定义。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, web_search, web_fetch, user_question
- **禁用工具（deny）**：agent_dispatch
- **写入路径**：docs/arch/, docs/research/
- **关联 Skill**：arc-design, tech-eval, context, research

</details>

<details>
<summary><b>4. ui-designer</b> — UI 设计师（界面 / 交互规范）</summary>

- **职责**：界面设计、交互规范、组件规格定义。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, web_search, web_fetch, user_question
- **禁用工具（deny）**：agent_dispatch
- **写入路径**：docs/ui-spec/, docs/research/
- **关联 Skill**：ui-design, context, research, penpot-bridge（条件启用）

</details>

<details>
<summary><b>5. tech-lead</b> — 技术主管（任务分解 / 开发计划）</summary>

- **职责**：功能到任务的分解、开发计划编排、TDD 模式判定（light vs standard）。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question
- **禁用工具（deny）**：agent_dispatch, web_search, web_fetch
- **写入路径**：docs/dev-plan/, docs/research/
- **关联 Skill**：task-decomp, task-dep-analysis, context

</details>

<details>
<summary><b>6. test-writer</b> — TDD RED 阶段（编写失败测试）</summary>

- **职责**：根据验收标准编写失败测试用例，所有测试必须 FAIL。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具（deny）**：agent_dispatch, web_search, web_fetch, user_question
- **写入路径**：src/, tests/
- **关联 Skill**：无

</details>

<details>
<summary><b>7. implementer</b> — TDD GREEN 阶段（最小实现）</summary>

- **职责**：编写最小实现代码使测试通过，支持 light 模式（合并 RED+GREEN）。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具（deny）**：agent_dispatch, web_search, web_fetch, user_question
- **写入路径**：src/, tests/
- **关联 Skill**：penpot-bridge（条件启用）

</details>

<details>
<summary><b>8. refactorer</b> — TDD REFACTOR 阶段（优化代码质量）</summary>

- **职责**：在测试全部通过的前提下优化代码质量；若重构后测试失败，状态回滚为 rolled-back。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具（deny）**：agent_dispatch, web_search, web_fetch, user_question
- **写入路径**：src/, tests/
- **关联 Skill**：无

</details>

<details>
<summary><b>9. reviewer</b> — 评审员（文档 + 代码跨阶段审查）</summary>

- **职责**：跨阶段质量审查，覆盖文档审查与代码审查。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具（deny）**：agent_dispatch
- **写入路径**：docs/reviews/doc/, docs/reviews/code/, docs/reviews/sprint/（严格限制）
- **关联 Skill**：context, code-review, sprint-review, penpot-bridge（条件启用）

</details>

<details>
<summary><b>10. qa-engineer</b> — 测试工程师（测试策略 / 集成 / E2E）</summary>

- **职责**：测试策略制定、集成测试与端到端测试编写、覆盖率分析、缺陷记录。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question
- **禁用工具（deny）**：agent_dispatch, web_search, web_fetch
- **写入路径**：docs/test-report/, src/, tests/
- **关联 Skill**：testing, context

</details>

<details>
<summary><b>11. devops</b> — 运维工程师（CI/CD / 容器化 / 发布）</summary>

- **职责**：CI/CD 流水线、容器化配置、基础设施即代码、发布规范。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具（deny）**：agent_dispatch, user_question, web_search, web_fetch
- **写入路径**：docs/deploy-spec/, docs/changelog/
- **关联 Skill**：deploy-config, context

</details>

<details>
<summary><b>12. debugger</b> — 调试工程师（运行时诊断 / 最小修复）</summary>

- **职责**：运行时错误诊断、根因分析、最小修复。按需或由编排器触发。
- **允许工具（allow）**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question
- **禁用工具（deny）**：agent_dispatch, web_search, web_fetch
- **写入路径**：src/, tests/, .cataforge/scripts/, .cataforge/hooks/, .cataforge/skills/
- **关联 Skill**：debug, context

</details>

<details>
<summary><b>13. reflector</b> — 反思者（跨项目经验提取）</summary>

- **职责**：从评审历史中提取跨项目经验教训，生成 EXP 条目和 SKILL-IMPROVE 建议。
- **允许工具（allow）**：file_read, file_edit, file_glob, file_grep
- **禁用工具（deny）**：agent_dispatch, user_question, shell_exec, web_search, web_fetch
- **写入路径**：docs/reviews/retro/, docs/reviews/CORRECTIONS-LOG.md, docs/EVENT-LOG.jsonl, .cataforge/learnings/
- **关联 Skill**：context

</details>

---

## Skill 清单（26 个）

### 总览

| # | Skill ID | 类型 | 领域 | 简要说明 |
|---|----------|------|------|---------|
| 1 | agent-dispatch | 核心框架 | 编排 | 子代理调度与运行时翻译 |
| 2 | context | 核心框架 | 上下文 | 统一上下文 I/O：navigate（段落精准加载）/ generate（文档生成、模板实例化、拆分）/ review（文档双层审计）/ consistency（跨文档语义一致性校验）/ query（知识图谱只读 SPARQL 问答）五个分支；review / consistency 分支由内置 Layer-1 引擎支撑 |
| 3 | code-review | 核心框架 | 质量 | 代码质量、合规性、安全性审查 |
| 4 | tdd-engine | 核心框架 | 开发 | TDD RED→GREEN→REFACTOR 三阶段编排 |
| 5 | arc-design | 领域技能 | 架构 | 模块划分、接口定义、数据建模 |
| 6 | ui-design | 领域技能 | 设计 | 页面布局、组件规格、交互流程 |
| 7 | task-decomp | 领域技能 | 计划 | 功能到任务的分解 |
| 8 | task-dep-analysis | 领域技能 | 计划 | 依赖建模、关键路径、循环检测 |
| 9 | tech-eval | 领域技能 | 架构 | 技术方案对比与选型决策 |
| 10 | req-analysis | 领域技能 | 需求 | 需求分解、用户故事、验收标准定义 |
| 11 | research | 领域技能 | 信息 | Web 搜索、用户访谈、信息收集 |
| 12 | change-guard | 核心框架 | 治理 | 变更请求分析与路由 |
| 13 | testing | 测试质量 | 测试 | 测试策略、测试编写、覆盖率分析 |
| 14 | sprint-review | 测试质量 | 回顾 | Sprint 完成度审查、AC 覆盖、范围偏移检测 |
| 15 | deploy-config | 部署运维 | 部署 | CI/CD 流水线、容器化、基础设施即代码 |
| 16 | debug | 部署运维 | 调试 | 结构化错误定位、根因分析、最小修复 |
| 17 | penpot-bridge | 设计集成 | 设计 | Penpot 设计↔代码桥：read/sync/generate/verify（条件启用） |
| 18 | platform-audit | 管理技能 | 平台 | 平台能力审计、profile.yaml 更新 |
| 19 | start-orchestrator | 管理技能 | 启动 | CataForge 工作流初始化与恢复 |
| 20 | workflow-framework-generator | 管理技能 | 生成 | 根据工作流类型与目标平台生成完整框架 |
| 21 | framework-update | 管理技能 | 同步 | 包↔scaffold 版本检测 + pip/uv 升级 + scaffold 刷新/部署/doctor + 项目初始化/恢复分流 |
| 22 | framework-review | 测试质量 | 元审计 | 元资产 (agents/skills/hooks/rules/workflow) 质量审计 — 必备段落、跨引用、SKILL.md ↔ CHECKS_MANIFEST 漂移、常量字面量、phase × agent 覆盖 |
| 23 | framework-feedback | 管理技能 | 反馈 | 下游 → 上游反馈打包：聚合 doctor + EVENT-LOG + `upstream-gap` corrections + framework-review FAIL → 渲染为 markdown，通过 `cataforge feedback` CLI 或本 skill 发出（`--print` / `--out` / `--clip` / `--gh`） |
| 24 | framework-issue-resolve | 管理技能 | 反馈 | 上游 maintainer 侧 GitHub issue 全闭环：拉取 (`cataforge issue triage`) → 审查分析（写 `docs/reviews/triage/SKILL-IMPROVE-<id>-issue-<N>.md` 草稿，verdict ∈ `confirmed` / `wontfix-by-design` / `already-fixed` / `needs-repro` / `unrelated`）→ 给修复意见 → 实施（feature branch + PR）→ 关闭 (`cataforge issue close <N> --verdict {fixed|wontfix|already-fixed} ...`)；3↔4 步是人工 go/no-go |
| 25 | framework-walkthrough | 测试质量 | 元自测 | 隔离沙盒内端到端跑通小型示例项目的完整 SDLC 工作流，观察各阶段/门禁/降级行为，产出框架本身与走查流程两类改进建议；framework-review 的动态对偶 |
| 26 | project-visualization | 核心框架 | 可视化 | 把既有 KG / doc-index / EVENT-LOG / CORRECTIONS / agent-skill 资产渲染为图 / 时间线 / 指标看板；薄发现型 skill 引导工作流按情境调 `cataforge viz <视图>`，orchestrator 在 Sprint 收口产出健康度看板 |

### 详细说明

> 按类别分组，点击展开查看详细说明。

<details>
<summary><b>核心框架 Skill</b>（agent-dispatch · context · code-review · tdd-engine · change-guard · project-visualization）</summary>

**agent-dispatch** — 子代理调度与运行时翻译
- 负责将编排器的 agent 调度请求翻译为目标平台的原生调度格式
- 包含调度 prompt 模板（支持平台覆盖：Cursor / Codex）

**context** — 统一上下文 I/O，分五个 reference 分支：
- **navigate** — 提供 `load_section` 能力，按 `{doc_id}#§{section}` 格式精准加载文档段落，避免全文读取，降低 agent 上下文占用
- **generate** — 统一文档生成，支持 standard（完整）/ lite（轻量）/ prototype（原型简报）三套模板体系；内置文档拆分，超过 DOC_SPLIT_THRESHOLD_LINES 自动分卷；模板目录 `.cataforge/skills/context/templates/`
- **review** — 文档双层审计，Layer 1 脚本化检查（结构完整性、格式合规性）+ Layer 2 AI 审查（语义一致性、业务逻辑正确性）；轻量文档类型（brief、prd-lite 等）可跳过 Layer 2；Layer 1 由内置引擎 `cataforge skill run doc-review` 支撑
- **consistency** — 跨文档语义一致性校验，PRD↔ARCH AC 追踪、ARCH↔DEV-PLAN API 契约、PRD↔UI-SPEC 用户可见性覆盖；输出 F-NNN 追踪矩阵 + 严重等级问题清单；退出码 0 全部通过 / 1 存在 CRITICAL/HIGH / 2 仅 MEDIUM/LOW，由 Phase Transition Protocol §5.5 在 Phase 2+ 转换时调用；Layer 1 由内置引擎 `cataforge skill run doc-consistency` 支撑
- **query** — 知识图谱自然语言查询，把问题翻译为只读 SPARQL 检索项目追溯关系并作答；schema card 由 `cataforge kg schema-context` 提供，执行与写守卫复用 `cataforge kg query`

**code-review** — 代码双层审查
- Layer 1：lint 工具检查（ruff 等）
- Layer 2：AI 审查（架构合规性、安全性、业务逻辑）
- 输出标准化评审报告

**tdd-engine** — TDD 三阶段引擎
- 编排 RED（test-writer）→ GREEN（implementer）→ REFACTOR（refactorer，条件触发）
- 默认 light 模式（RED+GREEN 合并）；LOC > `TDD_LIGHT_LOC_THRESHOLD`（默认 150）/ `security_sensitive` / 跨模块时升 standard
- agile-prototype 走 implementer 主线程内联，无子代理调度
- `task_kind ∈ {chore, config, docs}` 跳过 TDD，仅 implementer 单次实现 + lint hook

**change-guard** — 变更守卫
- 分析变更请求与现有文档的一致性
- 路由变更到适当的处理路径（文档修订 / 代码修改 / 新功能）

**project-visualization** — 项目可视化（薄发现型 skill，驱动 `cataforge viz` CLI）
- 把既有 KG / doc-index / EVENT-LOG / CORRECTIONS / agent-skill 资产渲染为图 / 时间线 / 指标看板，经 `cataforge viz <视图>` CLI 调用
- 情境→视图映射承载「定向」：覆盖盲区→`coverage`、追溯断链→`trace`、架构核对→`arch`、健康度总览→`dashboard`
- `user-invocable: false`（不经 `skill run`）；orchestrator 在 Sprint 收口确定性产出 `docs/viz/dashboard.html` 作保底

</details>

<details>
<summary><b>领域 Skill</b>（arc-design · ui-design · task-decomp · task-dep-analysis · tech-eval · req-analysis · research）</summary>

**arc-design** — 架构设计技能，涵盖模块划分、接口定义、数据建模。

**ui-design** — UI 设计技能，涵盖页面布局、组件规格、交互流程定义。

**task-decomp** — 任务分解技能，将功能需求拆解为可执行的开发任务。

**task-dep-analysis** — 依赖分析技能，建模任务间依赖关系，识别关键路径，检测循环依赖。

**tech-eval** — 技术评估技能，对备选技术方案进行对比分析并给出选型建议。

**req-analysis** — 需求分析技能，将粗粒度需求分解为结构化的用户故事和验收标准。

**research** — 调研技能，通过 Web 搜索和用户访谈收集决策所需信息。

</details>

<details>
<summary><b>测试与质量 Skill</b>（testing · sprint-review · framework-review）</summary>

**testing** — 测试技能，制定测试策略、编写测试用例、分析覆盖率、记录缺陷。

**sprint-review** — Sprint 回顾技能，审查 Sprint 完成度、AC 覆盖率、范围偏移检测。

**framework-review** — 元资产质量审计（v0.1.15 引入）。`scope=agents|skills|hooks|rules|workflow|all`，6 个子检查 B1-α/β、B2-α、B3-α、B4-α、B5-α — 必备段落、跨引用、SKILL.md ↔ CHECKS_MANIFEST 漂移检测、常量字面量替换、phase × agent 覆盖。报告写入 `docs/reviews/framework/`。CI 必备 gate（同 doctor）。

</details>

<details>
<summary><b>部署与运维 Skill</b>（deploy-config · debug）</summary>

**deploy-config** — 部署配置技能，生成 CI/CD 流水线、容器化配置、基础设施即代码模板。

**debug** — 调试技能，提供结构化错误定位、根因分析和最小修复方案。

</details>

<details>
<summary><b>设计工具集成 Skill</b>（penpot-bridge，条件启用，需设置 <code>design-tool: penpot</code>）</summary>

**penpot-bridge** — Penpot 设计↔代码桥，四操作：`read`（读结构/样式/Token 实值）、`sync`（Token 双向同步）、`generate`（从设计生成组件骨架）、`verify`（设计↔代码一致性校验，reviewer 独占）。

</details>

<details>
<summary><b>管理 Skill</b>（platform-audit · start-orchestrator · workflow-framework-generator · framework-update · framework-feedback）</summary>

**platform-audit** — 平台能力审计，检查各平台的 profile.yaml 与实际能力匹配度。

**start-orchestrator** — CataForge 工作流启动入口，负责初始化和恢复编排流程。

**workflow-framework-generator** — 工作流框架生成器，根据用户指定的工作流类型（软件开发、内容创作、电商运营、研究分析等）与目标 AI IDE 平台（Claude Code / Cursor / CodeX / OpenCode），自动生成一套完整的 CataForge 兼容框架。包含 Agent 定义、Skill 模块、Workflow 编排、平台适配配置等。内置 6 大领域模式库、四平台能力矩阵、框架校验脚本。

**framework-update** — CataForge 框架同步。三个指令：`check`（检测已安装包与项目 scaffold 的版本差异 + 项目初始化状态）、`apply`（条件包升级 → `cataforge bootstrap` 刷新 scaffold / 部署 / doctor → upgrade.state 与框架版本簿记 → 按项目指令文件存在与否分流项目初始化或恢复）、`verify`（运行迁移检查验证一致性）。支持 pip 与 uv 两种包管理器；保留 `runtime.platform`、`upgrade.state` 等用户可编辑状态。

**framework-feedback** — 下游 → 上游反馈打包（v0.3.0 引入）。聚合 `cataforge doctor` + 最近 `EVENT-LOG` + `CORRECTIONS-LOG` 中 `deviation=upstream-gap` 的纠偏 + `framework-review` Layer 1 FAIL 摘要为单个 markdown body，通过等价 CLI `cataforge feedback bug|suggest|correction-export` 经四选一互斥 sink 发出（`--print` / `--out PATH` / `--clip` / `--gh`）。命名上与 `framework-review` 平行（都针对 `.cataforge/` 框架本体），与下游产品自身的用户反馈渠道无关。`record-to-event-log: true`，每次运行写一条 `state_change` 事件（`ref=skill:framework-feedback/...`）。挂在 `orchestrator.skills`（持有 `shell_exec`）；reflector 因为是只读 Agent，不直接持有此 skill。详细参数见 [`cli.md` §feedback](./cli.md#feedback)。

</details>

---

## Agent-Skill 关联矩阵

每个 Agent 的默认装配与条件启用技能如下：

| Agent | 默认启用 Skill | 条件启用 |
|-------|---------------|---------|
| **orchestrator** | `agent-dispatch` · `context` · `tdd-engine` · `change-guard` · `framework-feedback` | — |
| **product-manager** | `req-analysis` · `context` · `research` | — |
| **architect** | `arc-design` · `tech-eval` · `context` · `research` | — |
| **ui-designer** | `ui-design` · `context` · `research` | `penpot-bridge` |
| **tech-lead** | `task-decomp` · `task-dep-analysis` · `context` | — |
| **test-writer** | — | — |
| **implementer** | — | `penpot-bridge` |
| **refactorer** | — | — |
| **reviewer** | `context` · `code-review` · `sprint-review` | `penpot-bridge` |
| **qa-engineer** | `testing` · `context` | — |
| **devops** | `deploy-config` · `context` | — |
| **debugger** | `debug` · `context` | — |
| **reflector** | `context` | — |

> **条件启用**由 `design-tool` 配置触发（如 `design-tool: penpot` 时启用 `penpot-bridge`）。

### 独立 Skill（不绑定 Agent）

这四个 Skill 由用户直接调用，不归属某个 Agent：

| Skill | 类型 | 典型触发 |
|-------|------|---------|
| `platform-audit` | 管理 | 审计 `profile.yaml` 与平台实际能力匹配度 |
| `start-orchestrator` | 管理 | 初始化 / 恢复 CataForge 工作流 |
| `workflow-framework-generator` | 管理 | 按工作流类型 + 目标平台生成完整框架 |
| `framework-update` | 管理 | 升级 CataForge 包 + 刷新 scaffold + 跑迁移检查 + 项目初始化/恢复 |
