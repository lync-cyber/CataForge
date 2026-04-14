# 通用行为规则 (COMMON-RULES)

## 全局约定
- 遵循 CLAUDE.md 效率原则中的全局约定
- Agent间传递 doc_id#section 引用，非全文复制
- 单一事实来源: 每条规则只在一个文件中定义完整内容，其他文件通过"见 {文件}#{章节}"引用，不重述
- 不确定时通过 research skill 调研，不猜测 (详见 .cataforge/skills/research/SKILL.md)
- 选择题优先：需要用户输入时优先提供选项

## 输出语言
- 所有Agent产出的文档、审查报告、RETRO报告、用户交互均使用**中文**
- 例外: 代码、变量命名、CLI参数、框架参数（doc_type/template_id等）使用英文
- 枚举值（status codes、category、root_cause、severity 等）始终使用英文，即使在中文文本中也不翻译。示例: "问题严重等级为 CRITICAL" 而非 "问题严重等级为严重"

## 统一状态码（共7个）
> 权威枚举定义见 `.cataforge/schemas/agent-result.schema.json`; 本表为语义说明。

所有Agent和子代理返回的状态码使用以下枚举:

| 状态码 | 含义 | 使用场景 | orchestrator处理 |
|--------|------|---------|-----------------|
| completed | 任务正常完成 | 所有Agent、TDD子代理 | 提取outputs，进入下一步 |
| needs_input | 需要用户输入才能继续 | 所有Agent | 进入Interrupt-Resume Protocol |
| blocked | 无法继续，需外部干预 | TDD子代理、任何Agent遇到不可恢复错误 | 记录阻塞原因，请求人工介入，不自动重试 |
| rolled-back | 重构失败已回滚 | REFACTOR子代理 | 使用GREEN阶段产出，标记MEDIUM |
| approved | 审查通过，无问题 | reviewer | 执行 Phase Transition Protocol |
| approved_with_notes | 审查通过但有MEDIUM/LOW建议（无CRITICAL/HIGH时触发） | reviewer | 向用户展示问题列表，用户选择"接受并继续"或"要求修复" |
| needs_revision | 审查不通过(有CRITICAL/HIGH) | reviewer | 进入Revision Protocol |

## 通用 Error Handling
所有Agent遇到以下场景时按统一策略处理:

| 场景 | 处理策略 |
|------|---------|
| 输入信息模糊/不完整 | 通过research skill的user-interview指令向用户确认(选择题优先，每批≤3题) |
| 上游文档间存在矛盾 | 以上游权威文档为准(PRD→ARCH→DEV-PLAN)，标注差异并在当前文档备注 |
| 所需信息缺失且无法从用户获取 | 标注[ASSUMPTION]给出合理默认值，确保可追溯 |
| 技术方案存在多个合理选项 | 通过tech-eval或research记录对比，标注推荐项和理由 |

## 框架配置常量
以下常量为框架级参数，各文件引用时以本节为准。**禁止在 SKILL.md / AGENT.md / 模板中硬编码同一数值**，应直接引用常量名（COMMON-RULES 默认加载到 Agent 上下文，无需附加引用路径说明）。

| 常量名 | 值 | 说明 | 引用方 |
|--------|-----|------|--------|
| MAX_QUESTIONS_PER_BATCH | 3 | 每批向用户提问的最大问题数 | product-manager, reviewer, research |
| MANUAL_REVIEW_CHECKPOINTS | [pre_dev, pre_deploy] | 阶段转换时需用户确认才能继续的检查点 | orchestrator |
| EVENT_LOG_PATH | docs/EVENT-LOG.jsonl | 统一事件日志路径（JSONL 格式） | event_logger.py, ORCHESTRATOR-PROTOCOLS |
| EVENT_LOG_SCHEMA | .cataforge/schemas/event-log.schema.json | 事件日志 Schema 定义 | event_logger.py |
| DOC_SPLIT_THRESHOLD_LINES | 300 | 单文档触发拆分的行数 | doc-gen |
| DOC_REVIEW_L2_SKIP_THRESHOLD_LINES | 200 | 文档行数低于此值且 Layer 1 通过时可跳过 Layer 2 | doc-review |
| DOC_REVIEW_L2_SKIP_DOC_TYPES | [brief, prd-lite, arch-lite, dev-plan-lite, changelog] | 可短路 Layer 2 的文档类型白名单 | doc-review |
| TDD_LIGHT_LOC_THRESHOLD | 50 | tech-lead 判定任务标记 `tdd_mode: light` 的预估 LOC 阈值 | tech-lead, tdd-engine |
| SPRINT_REVIEW_MICRO_TASK_COUNT | 2 | Sprint 任务数 ≤ 此值且全部 approved 时可跳过 sprint-review | orchestrator |
| RETRO_TRIGGER_SELF_CAUSED | 5 | CORRECTIONS-LOG 中 `hard`+`review` 条目累计达此值才触发 retrospective（`soft` 条目不计；自 2→5 以补偿 hook 自动捕获的高频 option-override 信号） | orchestrator, reflector |

### MANUAL_REVIEW_CHECKPOINTS 可选值
| 值 | 触发时机 | 说明 |
|----|---------|------|
| phase_transition | 每次阶段转换 | 所有 Phase N→N+1 均暂停确认（最严格） |
| pre_dev | Phase 4→5 转换前 | 开发阶段成本最高，确认开发计划和资源投入 |
| pre_deploy | Phase 6→7 转换前 | 部署前 go/no-go 决策 |
| post_sprint | 每个 Sprint Review 通过后 | 确认是否继续下一 Sprint 或调整优先级 |
| none | — | 完全自动推进，仅保留现有失败驱动的门禁 |

规则:
- 默认值 `[pre_dev, pre_deploy]` 覆盖最高风险节点
- 用户可在 Bootstrap 时或运行中通过修改 CLAUDE.md §全局约定 覆盖
- `none` 与其他值互斥，设为 `none` 时忽略列表中其他值
- `phase_transition` 已隐含 pre_dev 和 pre_deploy，不需重复列出

## 执行模式矩阵
框架支持三种执行模式，写入 CLAUDE.md §框架元信息.执行模式字段，未填时默认 `standard`。

| 维度 | standard（默认） | agile-lite | agile-prototype |
|------|-----------------|-----------|-----------------|
| 适用场景 | 中大型正式交付项目 | 5-10 feature 轻量工具/小型 Web 项目 | 原型 / PoC / 单文件脚本 |
| 阶段集合 | 7 阶段全跑，ui_design/testing/deployment 可配置 N/A | Phase 1+2 合并为 `planning`，development 保留，testing/deployment 可 N/A | Phase 1~4 合并为 `brief`，仅 `brief` + `development` |
| 文档产出 | PRD + ARCH + UI-SPEC + DEV-PLAN + TEST-REPORT + DEPLOY-SPEC | prd-lite + arch-lite + dev-plan-lite（各 ≤50 行） | 单一 brief.md（≤150 行） |
| doc-review | Layer 1 + Layer 2 强制 | Layer 1 强制；Layer 2 按 `DOC_REVIEW_L2_SKIP_*` 常量短路 | Layer 1 only |
| TDD 流程 | RED → GREEN → REFACTOR | RED+GREEN 合并（`tdd_mode: light`），REFACTOR 可选 | RED+GREEN 合并（`tdd_mode: light`），REFACTOR 跳过 |
| 人工检查点 | 引用 `MANUAL_REVIEW_CHECKPOINTS` | 仅 pre_dev | none |
| Sprint-review | 按 `SPRINT_REVIEW_MICRO_TASK_COUNT` 判定 | 同 standard | 跳过 |
| Retrospective | 按 `RETRO_TRIGGER_SELF_CAUSED` 判定 | 同 standard | 跳过 |

规则:
- `standard` 行为等价于未引入本矩阵前的 7 阶段流程，旧项目升级后无行为差异
- `agile-lite` / `agile-prototype` 仅适用于明确轻量的项目，由用户在 Bootstrap 时显式选择
- 模式切换由 orchestrator §Mode Routing Protocol 路由（见 .cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md）

## 文档引用格式
Agent 间传递文档引用时使用以下统一格式:

```
{doc_id}#§{section_number}[.{item_id}]
```

| 示例 | 含义 |
|------|------|
| `prd#§2` | PRD 文档第 2 章（功能需求） |
| `prd#§2.F-003` | PRD 文档第 2 章中的 F-003 条目 |
| `arch#§3.API-001` | 架构文档第 3 章中的 API-001 接口 |
| `dev-plan#§1` | 开发计划第 1 章（Sprint 规划表） |

规则:
- `doc_id` = template_id（见 doc-gen 映射表），如 prd、arch、dev-plan
- `section_number` 为纯数字（1, 2, 3...）
- `item_id` 为条目编号（F-xxx, M-xxx, API-xxx, E-xxx, T-xxx, C-xxx, P-xxx）
- 分卷文件的引用格式不变，doc-nav 负责定位到正确的分卷文件

## 输出质量原则

### 对比式约束
Anti-Patterns应使用"做A而非B"格式并附具体例子，避免抽象禁令:
- 差: "禁止: 未经调研直接选型"
- 好: "禁止: 未经调研直接选型 — 如不经对比就选择'React + PostgreSQL因为流行'，应通过tech-eval记录至少2个备选方案的对比矩阵"

### 具名默认倾向
当Agent可能受LLM默认倾向影响时，应在Anti-Patterns中点名该倾向:
- 示例(architect): "避免不假思索地套用'微服务 + PostgreSQL + Redis + Docker + Nginx'全家桶 — 小型项目单体架构可能更合适"
- 示例(product-manager): "避免给所有功能标P0 — P0是'没有则产品不可用'，大多数项目P0功能不超过总数40%"

### 决策记录要求
关键决策点（技术选型、架构风格、优先级排序）须在文档中留下可追溯的决策记录:
- 考虑了哪些选项
- 为什么选择当前方案
- 什么条件下应重新评估

## 通用 Anti-Patterns
- 禁止: 猜测项目状态，以 CLAUDE.md 和 docs/ 目录为唯一事实来源
- 禁止: 遗留未标注的 TODO/TBD/FIXME (必须标注 [ASSUMPTION])
- 禁止: 写入 CLAUDE.md 项目状态区 (orchestrator 专属)

## 统一问题分类体系
所有审查报告（文档审查和代码审查）使用以下统一分类:

| category | 适用范围 | 说明 |
|----------|---------|------|
| completeness | 文档+代码 | 逻辑缺失、定义不全 |
| consistency | 文档+代码 | 与上游/内部矛盾 |
| convention | 文档+代码 | 命名/格式/风格规范 |
| security | 文档+代码 | 安全漏洞、合规风险 |
| feasibility | 文档 | 技术可行性、实现性 |
| ambiguity | 文档 | 模糊不清、多义 |
| structure | 代码 | 架构/组织/耦合 |
| error-handling | 代码 | 异常处理、边界条件 |
| performance | 代码 | 性能/效率 |
| test-quality | 代码 | 测试断言有效性、测试逻辑正确性、边界覆盖 |

## 审查报告规范
所有审查报告（doc-review 和 code-review）共享以下规范。各 Skill 的 Layer 1 检查项和 Layer 2 审查维度分别定义在各自 SKILL.md 中。

### 报告编号规则
- 首次审查: `REVIEW-{doc_id}-r1.md` 或 `CODE-REVIEW-{task_id}-r1.md`
- 第 N 次审查: `-r{N}`（N = 对应子目录下同前缀 `-r*` 文件数 + 1）
- 最新版本 = 编号最大的文件，无需归档重命名

### 问题格式
```
### [R-{NNN}] {SEVERITY}: {标题}
- **category**: {问题分类，见 §统一问题分类体系}
- **root_cause**: {归因分类}
- **描述**: {问题描述}
- **建议**: {改进建议}
```

### 归因分类 (root_cause) 枚举
| root_cause | 含义 |
|------------|------|
| self-caused | 当前 Agent/开发者自身的遗漏或错误 |
| upstream-caused | 上游文档质量问题传导或定义不清导致的偏差 |
| input-caused | 用户输入不足或模糊 |
| reviewer-calibration | 审查标准争议 |

### 三态判定逻辑
| 条件 | 结论 |
|------|------|
| 存在 CRITICAL 或 HIGH 问题 | **needs_revision** |
| 无 CRITICAL/HIGH，但有 MEDIUM/LOW 问题 | **approved_with_notes** |
| 无问题 | **approved** |

