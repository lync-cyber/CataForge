# 通用行为规则 (COMMON-RULES)

本文件是 CataForge 各 Agent / Skill / Hook 共用的纪律与枚举单一事实来源；其他文件通过 `见 COMMON-RULES §<章节>` 引用，不重述。COMMON-RULES 默认加载到 Agent 上下文，引用时无需附加文件路径。

## 全局约定
- 遵循 CLAUDE.md 效率原则中的全局约定。
- Agent 间传递 `doc_id#§N[.item]` 引用，不复制全文。
- 单一事实来源：每条规则只在一个文件中定义完整内容，他处引用不重述。
- 不确定时通过 research skill 调研，不猜测（详见 `.cataforge/skills/research/SKILL.md`）。
- 选择题优先：需要用户输入时优先提供选项。
- 输出语言：所有 Agent 产出的文档 / 审查报告 / RETRO / 用户交互均使用**中文**；代码、变量命名、CLI 参数、框架参数（doc_type / template_id 等）使用英文；枚举值（status / category / root_cause / severity 等）始终英文，即使在中文文本中也不翻译——例：写"问题严重等级为 CRITICAL"而非"严重"。

## 框架配置常量
本表是框架级参数的单一事实来源。**禁止在 SKILL.md / AGENT.md / 模板中硬编码同一数值**，应直接引用常量名。

| 常量名 | 值 | 说明 | 引用方 |
|--------|-----|------|--------|
| MAX_QUESTIONS_PER_BATCH | 3 | 每批向用户提问的最大问题数 | product-manager, reviewer, research |
| MANUAL_REVIEW_CHECKPOINTS | [pre_dev, pre_deploy] | 阶段转换时需用户确认才能继续的检查点 | orchestrator |
| EVENT_LOG_PATH | docs/EVENT-LOG.jsonl | 统一事件日志路径（JSONL） | `cataforge event log`、ORCHESTRATOR-PROTOCOLS |
| EVENT_LOG_SCHEMA | .cataforge/schemas/event-log.schema.json | 事件日志 Schema | `cataforge event log`（核心校验在 `cataforge.core.event_log`） |
| DOC_SPLIT_THRESHOLD_LINES | 300 | 单文档触发拆分的行数 | doc-gen |
| META_DOC_SPLIT_THRESHOLD_LINES | 500 | SKILL.md / AGENT.md / 协议文档拆分提示行数（协议天然偏长） | framework-review |
| DOC_REVIEW_L2_SKIP_THRESHOLD_LINES | 200 | 文档行数低于此值且 Layer 1 通过时可跳过 Layer 2 | doc-review |
| DOC_REVIEW_L2_SKIP_DOC_TYPES | [brief, prd-lite, arch-lite, dev-plan-lite, changelog] | 可短路 Layer 2 的文档类型白名单 | doc-review |
| TDD_LIGHT_LOC_THRESHOLD | 150 | tech-lead 判定 `tdd_mode: standard` 的预估 LOC 上限阈值（LOC ≤ 阈值 → light；> 阈值 → standard） | tech-lead, tdd-engine |
| TDD_DEFAULT_MODE | light | 任务卡 `tdd_mode` 缺省值。LOC > 阈值或带 `security_sensitive: true` / 跨模块时 tech-lead 显式标 standard | tech-lead, tdd-engine |
| TDD_REFACTOR_TRIGGER | [complexity, duplication, coupling] | standard 模式下 REFACTOR 阶段的条件触发清单（GREEN 后 code-review Layer 1 命中任一 category 才调度 refactorer；任务卡显式 `tdd_refactor: required` 也强制触发） | tdd-engine |
| SPRINT_REVIEW_MICRO_TASK_COUNT | 3 | Sprint 任务数 ≤ 此值且全部 approved 时跳过 sprint-review | orchestrator |
| CODE_REVIEW_L2_SKIP_TASK_KINDS | [chore, config, docs] | 任务卡 `task_kind` 命中且 Layer 1 通过时短路 code-review Layer 2 | code-review |
| CODE_REVIEW_L2_SKIP_LIGHT_MAX_AC | 2 | light 模式下 AC 数 ≤ 此值且 Layer 1 通过时短路 code-review Layer 2（security/error-handling 关键字命中时不短路） | code-review |
| ADAPTIVE_REVIEW_DOWNGRADE_CLEAN_TASKS | 10 | 连续 N 个任务零 self-caused 问题时 Adaptive Review 反向降级（仅跑 Layer 1） | orchestrator |
| RETRO_TRIGGER_SELF_CAUSED | 5 | CORRECTIONS-LOG 中 `hard`+`review` 条目累计达此值触发 retrospective（`soft` 不计） | orchestrator, reflector |

### MANUAL_REVIEW_CHECKPOINTS 可选值
| 值 | 触发时机 | 说明 |
|----|---------|------|
| phase_transition | 每次阶段转换 | 所有 Phase N→N+1 暂停（最严格，隐含 pre_dev / pre_deploy） |
| pre_dev | Phase 4→5 前 | 开发阶段成本最高，确认开发计划与资源 |
| pre_deploy | Phase 6→7 前 | 部署 go/no-go |
| post_sprint | Sprint Review 通过后 | 是否继续下一 Sprint |
| none | — | 完全自动推进，仅保留失败驱动门禁 |

规则：默认 `[pre_dev, pre_deploy]` 覆盖最高风险节点；用户在 Bootstrap 时或运行中通过 CLAUDE.md §全局约定 覆盖；`none` 与其他值互斥。

## 执行模式矩阵
框架支持三种执行模式，写入 CLAUDE.md §框架元信息.执行模式，未填默认 `standard`。

| 维度 | standard（默认） | agile-lite | agile-prototype |
|------|-----------------|-----------|-----------------|
| 适用场景 | 中大型正式交付 | 5-10 feature 轻量项目 | 原型 / PoC / 单文件脚本 |
| 阶段集合 | 7 阶段全跑，ui_design / testing / deployment 可 N/A | Phase 1+2 合并为 `planning`；testing / deployment 可 N/A | Phase 1~4 合并为 `brief`，仅 `brief` + `development` |
| 文档产出 | PRD + ARCH + UI-SPEC + DEV-PLAN + TEST-REPORT + DEPLOY-SPEC | prd-lite + arch-lite + dev-plan-lite（各 ≤100 行）；UI 项目可选 ui-spec-lite | 单一 brief.md（≤200 行） |
| doc-review | Layer 1 + Layer 2 强制 | Layer 1 强制；Layer 2 按 `DOC_REVIEW_L2_SKIP_*` 短路 | Layer 1 only |
| TDD | 默认 light（RED+GREEN 合并）；LOC > `TDD_LIGHT_LOC_THRESHOLD` 或 `security_sensitive: true` / 跨模块时升 standard，REFACTOR 按 `TDD_REFACTOR_TRIGGER` 条件触发 | RED+GREEN 合并（`tdd_mode: light`），REFACTOR 仅在 code-review 命中 `TDD_REFACTOR_TRIGGER` 时触发 | implementer 主线程一次性写测试+实现，跳过 RED/GREEN/REFACTOR 子代理调度 |
| 人工检查点 | 引用 `MANUAL_REVIEW_CHECKPOINTS` | 仅 pre_dev | none |
| Sprint-review | 按 `SPRINT_REVIEW_MICRO_TASK_COUNT` 判定 | 同 standard | 跳过 |
| Retrospective | 按 `RETRO_TRIGGER_SELF_CAUSED` 判定 | 同 standard | 跳过 |

规则：`standard` 等价于未引入本矩阵前的 7 阶段流程；`agile-lite` / `agile-prototype` 由用户在 Bootstrap 显式选择；模式切换由 orchestrator §Mode Routing Protocol 路由（见 `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md`）。

## 统一状态码
权威枚举见 `.cataforge/schemas/agent-result.schema.json`；本表为语义说明。所有 Agent 与子代理返回值取自下表。

| 状态码 | 含义 | 使用场景 | orchestrator 处理 |
|--------|------|---------|------------------|
| completed | 任务正常完成 | 所有 Agent / TDD 子代理 | 提取 outputs，进入下一步 |
| needs_input | 需要用户输入 | 所有 Agent | 进入 Interrupt-Resume Protocol |
| blocked | 无法继续，需外部干预 | TDD / 任意 Agent 遇不可恢复错误 | 记录原因，请求人工，不自动重试 |
| rolled-back | 重构失败已回滚 | REFACTOR 子代理 | 用 GREEN 阶段产出，标 MEDIUM |
| approved | 审查通过，无问题 | reviewer | 执行 Phase Transition Protocol |
| approved_with_notes | 审查通过但有 MEDIUM/LOW（无 CRITICAL/HIGH） | reviewer | 展示问题，用户选"接受并继续"或"要求修复" |
| needs_revision | 审查不通过（有 CRITICAL/HIGH） | reviewer | 进入 Revision Protocol |

## 通用 Error Handling
| 场景 | 处理策略 |
|------|---------|
| 输入信息模糊 / 不完整 | 通过 research skill 的 user-interview 向用户确认（选择题优先，每批 ≤ MAX_QUESTIONS_PER_BATCH） |
| 上游文档间存在矛盾 | 以上游权威文档为准（PRD→ARCH→DEV-PLAN），标注差异 |
| 所需信息缺失且无法获取 | 标注 `[ASSUMPTION]` 给出合理默认值，确保可追溯 |
| 技术方案存在多个合理选项 | 通过 tech-eval / research 记录对比矩阵，标注推荐项 |

## 文档引用格式
Agent 间统一格式：

```
{doc_id}#§{section_number}[.{item_id}]
```

| 示例 | 含义 |
|------|------|
| `prd#§2` | PRD 第 2 章 |
| `prd#§2.F-003` | PRD 第 2 章 F-003 条目 |
| `arch#§3.API-001` | 架构第 3 章 API-001 接口 |

规则：`doc_id` = template_id（见 doc-gen 映射表）；`section_number` 为纯数字；`item_id` 为条目编号（F/M/API/E/T/C/P-xxx）；分卷文件引用格式不变，doc-nav 负责定位到正确分卷。

## 文档加载纪律
适用：所有 sub-agent 加载 `docs/` 下指定章节时（architect / tech-lead / qa-engineer / devops / ui-designer 等读 PRD/ARCH/UI-SPEC/DEV-PLAN 的角色，及任何用 doc_id#§N 做输入契约的下游）。

- 禁止：用 Read 工具一次性读取 `docs/{doc_type}/*.md` 整篇 — 几千行整篇会瞬间稀释焦点并浪费 token。
- 强制：通过 `cataforge docs load <doc_id>#§N[.item]` 按章节 / 条目维度按需分批加载；同文件多 ref 共享 per-file 缓存，批量调用优于循环。
- 各 agent 自己的 Input Contract 段落保留**该角色实际需要的 doc_id 白名单**，但不重复"禁止 Read 全文"这条通用规则。
- `cataforge docs load` 失败（exit 2 = 至少一个 ref 失败）按 stderr 提示修正；索引漂移时 `cataforge docs validate` 校验、`cataforge docs index` 重建。

## 输出质量原则

### 对比式约束
Anti-Patterns 应使用"做 A 而非 B"格式并附具体例子，避免抽象禁令：
- 差："禁止：未经调研直接选型"
- 好："禁止：未经调研直接选型 — 如不经对比就选择 'React + PostgreSQL 因为流行'，应通过 tech-eval 记录至少 2 个备选方案的对比矩阵"

### 具名默认倾向
当 Agent 可能受 LLM 默认倾向影响时，Anti-Patterns 中点名该倾向：
- architect："避免不假思索地套用 '微服务 + PostgreSQL + Redis + Docker + Nginx' 全家桶 — 小型项目单体架构可能更合适"
- product-manager："避免给所有功能标 P0 — P0 是 '没有则产品不可用'，大多数项目 P0 不超过 40%"

### 决策记录要求
关键决策点（技术选型、架构风格、优先级排序）须留下可追溯记录：考虑了哪些选项 / 为什么选择当前方案 / 什么条件下应重新评估。

### 禁止估算任务用时
适用：所有 Agent 的 backlog 排序、改进建议、PR 描述、todo / 计划、口头汇报。

- 禁止：附加"X 分钟 / 小时 / 天"之类的用时估算（含"半小时"、"1-2 小时"、"很快就好"等口语表述）。
- 原因：LLM 任务的执行节奏与人类完全不同（并行工具调用、零打字成本、无上下文切换），用人类工时估算 LLM 任务无参考价值并误导用户排期。
- 替代：用"成本 / 复杂度"维度——"单点改动"、"涉及多文件"、"需新写测试"、"需跨包重构"——不写绝对时间。
- 自检：写完一段建议或 todo 后搜索"分钟 / 小时 / 天 / quick / fast"，命中即删。

### 禁止设计阶段与变更说明残留
适用：源码、docstring、测试 docstring、SKILL.md / AGENT.md / 协议文档、配置 —— **新增和修改都生效**。CHANGELOG / commit message / PR 描述是变更说明的唯一合法去处，不能溢出到长期文档。

**新增时**：
- 禁止回溯叙事与动机自述："之前 / 原本 / used to / previously / 修复了 X / 解决了 ……失败模式 / 此测试为防 issue#NNN 再发"。
- 函数 docstring 只描述**当前职责**；测试名 + 断言已表达意图，docstring 通常一句即可。
- 默认不写注释；命名 + 小函数 > 注释。仅在保留**非显然 WHY**（隐式约束、易踩边界、非直观不变量）时写注释，单行优先、≤2 行。

**修改时**（默认不写变更说明）：
- 禁止版本里程碑（"v0.4.0+ 新增"、"自 vX.Y.Z 起"、"MVP 阶段"）、阶段标签（"先 MVP 后升级"、"以后再做"）、对比叙事（"原方案 X、改为 Y"、"不再使用 X"）。
- 直接覆盖陈述当前状态，不保留"现在改为……"句式。
- 移除字段 / 重命名 / 替换默认值时不留 deprecated 标记，让 commit diff 自身承载证据。
- 表格 / 配置项里只写当前生效值，不写"曾经是 X"。
- 保留语义价值的版本号写入 frontmatter `version:` / `min_version:` 字段，不放正文。

**自检**：写完段落后搜索 `之前|previously|used to|修复了|替代了|v[0-9]+\.[0-9]+\.[0-9]+ 新增|起|MVP|原|改为|之前是|现已废弃`，命中即删。

## 通用 Anti-Patterns
- 禁止：猜测项目状态——以 CLAUDE.md 和 `docs/` 目录为唯一事实来源。
- 禁止：遗留未标注的 TODO / TBD / FIXME（必须标注 `[ASSUMPTION]`）。强制由 doc-review Layer 1 检查器实现，参见 `cataforge.skill.builtins.doc_review.checker.check_no_todo`。
- 禁止：写入 CLAUDE.md 项目状态区（orchestrator 专属）。
- 禁止：硬编码 §框架配置常量 中已定义的数值（应直接引用常量名）。

## 统一问题分类体系
所有审查报告（doc-review / code-review / framework-review / sprint-review）共用以下分类。

| category | 适用范围 | 说明 |
|----------|---------|------|
| completeness | 文档+代码 | 逻辑缺失、定义不全 |
| consistency | 文档+代码 | 与上游 / 内部矛盾 |
| convention | 文档+代码 | 命名 / 格式 / 风格规范 |
| security | 文档+代码 | 安全漏洞、合规风险 |
| feasibility | 文档 | 技术可行性、实现性 |
| ambiguity | 文档 | 模糊不清、多义 |
| structure | 代码 | 架构 / 组织 / 职责划分 |
| error-handling | 代码 | 异常处理、边界条件 |
| performance | 代码 | 性能 / 效率 |
| test-quality | 代码 | 断言有效性、测试逻辑、边界覆盖 |
| duplication | 代码 | 跨文件 / 跨函数重复（Type-1/2 克隆，含 copy-paste 与近似克隆） |
| dead-code | 代码 | 不可达分支、未引用的导出、永远为假的条件 |
| complexity | 代码 | 圈 / 认知复杂度过高、嵌套深度超阈值 |
| coupling | 代码 | 模块间引用过密、依赖图循环或扇出过大 |

## Layer 1 调用协议
三个审查 Skill（`doc-review` / `code-review` / `sprint-review`）的 Layer 1 脚本统一通过 `cataforge skill run <skill-id> -- <args...>` 触发——由 `SkillRunner` 路由到内置实现（`python -m cataforge.skill.builtins.*`）或项目覆写脚本。**不得**在 SKILL.md / Agent / Hook 任何位置直写 `python .cataforge/skills/<id>/scripts/*.py`，该路径在仅发放 SKILL.md 的默认 scaffold 中不存在。完整规约见 [`docs/architecture/quality-and-learning.md §2.1`](../../docs/architecture/quality-and-learning.md)。

Layer 1 返回四态：`0` → 进入 Layer 2；`1` → 报问题不进 Layer 2；`2` / `127` / `CataforgeError("no executable scripts")` → **FAIL**（先 `cataforge doctor`）；运行时异常 / 超时 → 降级进入 Layer 2。

## 审查报告规范
所有审查报告（doc-review / code-review）共享以下规范。各 Skill 的 Layer 1 检查项与 Layer 2 维度分别定义在各自 SKILL.md。

### 报告编号规则
- 首次：`REVIEW-{doc_id}-r1.md` 或 `CODE-REVIEW-{task_id}-r1.md`。
- 第 N 次：`-r{N}`，N = 同前缀 `-r*` 文件数 + 1。
- 最新版本 = 编号最大的文件，无需归档重命名。

### 报告 Front Matter 约定
所有系统生成的报告（含审查报告与运维日志）必须以 YAML front matter 起始；缺失会被 `cataforge docs index` 跳过、被 `cataforge doctor` 计为 orphan 并 FAIL。

| 报告类别 | 路径 | `id` 格式 | `doc_type` | 允许 `status` |
|---------|------|----------|-----------|--------------|
| 文档审查报告 | `docs/reviews/doc/REVIEW-{doc_id}-r{N}.md` | `review-{doc_id}-r{N}` | `review` | `draft` / `approved` |
| 代码审查报告 | `docs/reviews/code/CODE-REVIEW-{task_id}-r{N}.md` | `code-review-{task_id}-r{N}` | `code-review` | `draft` / `approved` |
| Sprint 审查报告 | `docs/reviews/sprint/SPRINT-REVIEW-*.md` | 见 [`utility/sprint-review.md`](../skills/doc-gen/templates/utility/sprint-review.md) | `sprint-review` | `draft` / `approved` |
| 框架元资产审查 | `docs/reviews/framework/FRAMEWORK-REVIEW-{scope}-{YYYYMMDD}-r{N}.md` | `framework-review-{scope}-{YYYYMMDD}-r{N}` | `framework-review` | `draft` / `approved` |
| 项目级代码扫描 | `docs/reviews/code/CODE-SCAN-{YYYYMMDD}-r{N}.md` | `code-scan-{YYYYMMDD}-r{N}` | `code-review` | `draft` / `approved` |
| 运维订正日志 | `docs/reviews/CORRECTIONS-LOG.md` | `corrections-log` | `correction-log` | `approved` |

最小字段集（doc-review checker 强制 id / author / status / deps）：

```yaml
---
id: "review-{doc_id}-r{N}"        # 或 code-review-{task_id}-r{N} / corrections-log
doc_type: review                  # 或 code-review / sprint-review / correction-log
author: reviewer                  # 审查报告：reviewer；CORRECTIONS-LOG：cataforge
status: draft                     # 出 verdict 后改 approved；CORRECTIONS-LOG 恒为 approved
deps: ["{被审 doc_id 或 task_id}"] # CORRECTIONS-LOG 用 []
---
```

`status` 取值仅 `draft` / `review` / `approved`（见 doc-review checker），不可写 `closed`。

### 问题格式
```
### [R-{NNN}] {SEVERITY}: {标题}
- **category**: {见 §统一问题分类体系}
- **root_cause**: {见 §归因分类}
- **描述**: {问题描述}
- **建议**: {改进建议}
```

### 归因分类
| root_cause | 含义 |
|------------|------|
| self-caused | 当前 Agent / 开发者自身的遗漏或错误 |
| upstream-caused | 上游文档质量问题传导或定义不清导致的偏差 |
| input-caused | 用户输入不足或模糊 |
| reviewer-calibration | 审查标准争议 |

### 三态判定逻辑
| 条件 | 结论 |
|------|------|
| 存在 CRITICAL 或 HIGH | **needs_revision** |
| 无 CRITICAL/HIGH，但有 MEDIUM/LOW | **approved_with_notes** |
| 无问题 | **approved** |

