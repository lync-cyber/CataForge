# Agent 与 Skill 清单

本文档列出 CataForge 框架内置的所有 Agent 和 Skill，包括角色说明、可用工具、关联技能等信息。

> 源定义文件位于 `.cataforge/agents/` 和 `.cataforge/skills/` 目录。

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

#### 1. orchestrator（主编排智能体）

- **职责**：协调整个软件开发生命周期，负责项目引导（Bootstrap）、阶段路由、手动审查检查点、中断恢复协议、TDD 编排。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, agent_dispatch, user_question
- **写入路径**：无限制
- **关联 Skill**：agent-dispatch, doc-nav, tdd-engine, change-guard
- **特殊协议**：拥有专属编排协议（ORCHESTRATOR-PROTOCOLS.md），管理阶段转换、修订流程、Sprint 回顾触发等。

#### 2. product-manager（产品经理）

- **职责**：需求分析、用户故事编写、PRD 文档生成。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, web_search, web_fetch, user_question
- **禁用工具**：shell_exec, agent_dispatch
- **写入路径**：docs/prd/, docs/research/
- **关联 Skill**：req-analysis, doc-gen, doc-nav, research

#### 3. architect（架构师）

- **职责**：架构设计、技术选型、模块划分、接口定义。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, web_search, web_fetch, user_question
- **禁用工具**：agent_dispatch
- **写入路径**：docs/arch/, docs/research/
- **关联 Skill**：arc-design, tech-eval, doc-gen, doc-nav, research

#### 4. ui-designer（UI 设计师）

- **职责**：界面设计、交互规范、组件规格定义。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, web_search, web_fetch, user_question
- **禁用工具**：agent_dispatch
- **写入路径**：docs/ui-spec/, docs/research/
- **关联 Skill**：ui-design, doc-gen, doc-nav, research, penpot-sync（条件启用）

#### 5. tech-lead（技术主管）

- **职责**：功能到任务的分解、开发计划编排、TDD 模式判定（light vs standard）。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question
- **禁用工具**：agent_dispatch, web_search, web_fetch
- **写入路径**：docs/dev-plan/, docs/research/
- **关联 Skill**：task-decomp, dep-analysis, doc-gen, doc-nav

#### 6. test-writer（TDD RED 阶段）

- **职责**：根据验收标准编写失败测试用例，所有测试必须 FAIL。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具**：agent_dispatch, web_search, web_fetch, user_question
- **写入路径**：src/, tests/
- **关联 Skill**：无

#### 7. implementer（TDD GREEN 阶段）

- **职责**：编写最小实现代码使测试通过，支持 light 模式（合并 RED+GREEN）。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具**：agent_dispatch, web_search, web_fetch, user_question
- **写入路径**：src/, tests/
- **关联 Skill**：penpot-implement（条件启用）

#### 8. refactorer（TDD REFACTOR 阶段）

- **职责**：在测试全部通过的前提下优化代码质量；若重构后测试失败，状态回滚为 rolled-back。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具**：agent_dispatch, web_search, web_fetch, user_question
- **写入路径**：src/, tests/
- **关联 Skill**：无

#### 9. reviewer（评审员）

- **职责**：跨阶段质量审查，覆盖文档审查与代码审查。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具**：agent_dispatch
- **写入路径**：docs/reviews/doc/, docs/reviews/code/, docs/reviews/sprint/（严格限制）
- **关联 Skill**：doc-review, code-review, sprint-review, doc-nav, penpot-review（条件启用）

#### 10. qa-engineer（测试工程师）

- **职责**：测试策略制定、集成测试与端到端测试编写、覆盖率分析、缺陷记录。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question
- **禁用工具**：agent_dispatch, web_search, web_fetch
- **写入路径**：docs/test-report/, src/, tests/
- **关联 Skill**：testing, doc-gen, doc-nav

#### 11. devops（运维工程师）

- **职责**：CI/CD 流水线、容器化配置、基础设施即代码、发布规范。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec
- **禁用工具**：agent_dispatch, user_question, web_search, web_fetch
- **写入路径**：docs/deploy-spec/, docs/changelog/
- **关联 Skill**：deploy-config, doc-gen, doc-nav

#### 12. debugger（调试工程师）

- **职责**：运行时错误诊断、根因分析、最小修复。按需或由编排器触发。
- **可用工具**：file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question
- **禁用工具**：agent_dispatch, web_search, web_fetch
- **写入路径**：src/, tests/, .cataforge/scripts/, .cataforge/hooks/, .cataforge/skills/
- **关联 Skill**：debug, doc-nav

#### 13. reflector（反思者）

- **职责**：从评审历史中提取跨项目经验教训，生成 EXP 条目和 SKILL-IMPROVE 建议。
- **可用工具**：file_read, file_edit, file_glob, file_grep（以只读为主）
- **禁用工具**：agent_dispatch, user_question, shell_exec, web_search, web_fetch
- **写入路径**：docs/reviews/retro/, docs/reviews/CORRECTIONS-LOG.md, docs/EVENT-LOG.jsonl, .cataforge/learnings/
- **关联 Skill**：doc-nav

---

## Skill 清单（24 个）

### 总览

| # | Skill ID | 类型 | 领域 | 简要说明 |
|---|----------|------|------|---------|
| 1 | agent-dispatch | 核心框架 | 编排 | 子代理调度与运行时翻译 |
| 2 | doc-gen | 核心框架 | 文档 | 统一文档生成、模板实例化、文档拆分 |
| 3 | doc-nav | 核心框架 | 文档 | 文档导航与选择性段落加载 |
| 4 | doc-review | 核心框架 | 质量 | 文档双层审计（脚本 + AI） |
| 5 | code-review | 核心框架 | 质量 | 代码质量、合规性、安全性审查 |
| 6 | tdd-engine | 核心框架 | 开发 | TDD RED→GREEN→REFACTOR 三阶段编排 |
| 7 | arc-design | 领域技能 | 架构 | 模块划分、接口定义、数据建模 |
| 8 | ui-design | 领域技能 | 设计 | 页面布局、组件规格、交互流程 |
| 9 | task-decomp | 领域技能 | 计划 | 功能到任务的分解 |
| 10 | dep-analysis | 领域技能 | 计划 | 依赖建模、关键路径、循环检测 |
| 11 | tech-eval | 领域技能 | 架构 | 技术方案对比与选型决策 |
| 12 | req-analysis | 领域技能 | 需求 | 需求分解、用户故事、验收标准定义 |
| 13 | research | 领域技能 | 信息 | Web 搜索、用户访谈、信息收集 |
| 14 | change-guard | 核心框架 | 治理 | 变更请求分析与路由 |
| 15 | testing | 测试质量 | 测试 | 测试策略、测试编写、覆盖率分析 |
| 16 | sprint-review | 测试质量 | 回顾 | Sprint 完成度审查、AC 覆盖、范围偏移检测 |
| 17 | deploy-config | 部署运维 | 部署 | CI/CD 流水线、容器化、基础设施即代码 |
| 18 | debug | 部署运维 | 调试 | 结构化错误定位、根因分析、最小修复 |
| 19 | penpot-sync | 设计集成 | 设计 | Design Token 双向同步（条件启用） |
| 20 | penpot-implement | 设计集成 | 设计 | 从 Penpot 生成组件代码骨架（条件启用） |
| 21 | penpot-review | 设计集成 | 设计 | 设计-代码一致性验证（条件启用） |
| 22 | platform-audit | 管理技能 | 平台 | 平台能力审计、profile.yaml 更新 |
| 23 | start-orchestrator | 管理技能 | 启动 | CataForge 工作流初始化与恢复 |
| 24 | workflow-framework-generator | 管理技能 | 生成 | 根据工作流类型与目标平台生成完整框架 |

### 详细说明

#### 核心框架 Skill

**agent-dispatch** — 子代理调度与运行时翻译
- 负责将编排器的 agent 调度请求翻译为目标平台的原生调度格式
- 包含调度 prompt 模板（支持平台覆盖：Cursor / Codex）

**doc-gen** — 统一文档生成
- 支持三套模板体系：standard（完整）、lite（轻量）、prototype（原型简报）
- 内置文档拆分功能，超过 DOC_SPLIT_THRESHOLD_LINES 自动分卷
- 模板目录：`.cataforge/skills/doc-gen/templates/`

**doc-nav** — 文档导航与段落加载
- 提供 `load_section` 能力，按 `{doc_id}#§{section}` 格式精准加载文档段落
- 避免全文读取，降低 agent 上下文占用

**doc-review** — 文档双层审计
- Layer 1：脚本化检查（结构完整性、格式合规性）
- Layer 2：AI 审查（语义一致性、业务逻辑正确性）
- 对轻量文档类型（brief、prd-lite 等）可跳过 Layer 2

**code-review** — 代码双层审查
- Layer 1：lint 工具检查（ruff 等）
- Layer 2：AI 审查（架构合规性、安全性、业务逻辑）
- 输出标准化评审报告

**tdd-engine** — TDD 三阶段引擎
- 编排 RED（test-writer）→ GREEN（implementer）→ REFACTOR（refactorer）
- 支持 standard 和 light 两种模式（light 模式合并 RED+GREEN）
- light 模式阈值：TDD_LIGHT_LOC_THRESHOLD（默认 50 LOC）

**change-guard** — 变更守卫
- 分析变更请求与现有文档的一致性
- 路由变更到适当的处理路径（文档修订 / 代码修改 / 新功能）

#### 领域 Skill

**arc-design** — 架构设计技能，涵盖模块划分、接口定义、数据建模。

**ui-design** — UI 设计技能，涵盖页面布局、组件规格、交互流程定义。

**task-decomp** — 任务分解技能，将功能需求拆解为可执行的开发任务。

**dep-analysis** — 依赖分析技能，建模任务间依赖关系，识别关键路径，检测循环依赖。

**tech-eval** — 技术评估技能，对备选技术方案进行对比分析并给出选型建议。

**req-analysis** — 需求分析技能，将粗粒度需求分解为结构化的用户故事和验收标准。

**research** — 调研技能，通过 Web 搜索和用户访谈收集决策所需信息。

#### 测试与质量 Skill

**testing** — 测试技能，制定测试策略、编写测试用例、分析覆盖率、记录缺陷。

**sprint-review** — Sprint 回顾技能，审查 Sprint 完成度、AC 覆盖率、范围偏移检测。

#### 部署与运维 Skill

**deploy-config** — 部署配置技能，生成 CI/CD 流水线、容器化配置、基础设施即代码模板。

**debug** — 调试技能，提供结构化错误定位、根因分析和最小修复方案。

#### 设计工具集成 Skill（条件启用，需设置 `design-tool: penpot`）

**penpot-sync** — Design Token 双向同步，在 Penpot 设计工具和代码间同步设计令牌。

**penpot-implement** — 从 Penpot 设计稿生成组件代码骨架。

**penpot-review** — 验证代码实现与 Penpot 设计稿的一致性。

#### 管理 Skill

**platform-audit** — 平台能力审计，检查各平台的 profile.yaml 与实际能力匹配度。

**start-orchestrator** — CataForge 工作流启动入口，负责初始化和恢复编排流程。

**workflow-framework-generator** — 工作流框架生成器，根据用户指定的工作流类型（软件开发、内容创作、电商运营、研究分析等）与目标 AI IDE 平台（Claude Code / Cursor / CodeX / OpenCode），自动生成一套完整的 CataForge 兼容框架。包含 Agent 定义、Skill 模块、Workflow 编排、平台适配配置等。内置 6 大领域模式库、四平台能力矩阵、框架校验脚本。

---

## Agent-Skill 关联矩阵

```text
                  agent  doc   doc   doc   code  tdd   arc   ui    task  dep   tech  req   re-   change testing sprint deploy debug penpot penpot penpot platform start  wf-fw
                  disp   gen   nav   rev   rev   eng   des   des   dec   ana   eval  ana   search guard                config       sync   impl   rev    audit    orch   gen
orchestrator       *            *                 *                                        *
product-manager          *     *                              *                 *     *
architect                *     *                        *                 *           *
ui-designer              *     *                              *                      *                                        ?
tech-lead                *     *                                    *     *
test-writer
implementer                                                                                                                         ?
refactorer
reviewer                       *     *     *                                               *      *                                        ?
qa-engineer              *     *                                                                  *
devops                   *     *                                                                         *
debugger                       *                                                                                *
reflector                      *
（独立）                                                                                                                                                          *      *
```

图例：`*` = 默认启用，`?` = 条件启用（依赖 design-tool 配置），`（独立）` = 用户直接调用的独立 Skill，不绑定特定 Agent
