# 状态码与引用格式

> CataForge 运行时的统一状态码、文档引用格式、事件日志规范。
>
> **适用版本**：以 `cataforge --version` 为准（= `cataforge.__version__`）。常量定义以 [`cataforge.interface.cli.errors`](../../src/cataforge/interface/cli/errors.py) 为权威。

## 1. Agent 状态码

所有 Agent 返回统一的状态码：

| 状态码 | 含义 | 后续动作 |
|-------|------|---------|
| `completed` | 正常完成 | 进入审查 |
| `needs_input` | 需要用户决策 | 中断恢复协议 |
| `blocked` | 需要外部干预 | 暂停等待 |
| `rolled-back` | REFACTOR 失败，保留 GREEN 输出 | 记录并继续 |
| `approved` | 审查通过 | 阶段转换 |
| `approved_with_notes` | 通过但有建议 | 用户选择接受或修复 |
| `needs_revision` | 存在严重问题 | 修订协议 |

相关协议：[`../architecture/runtime-workflow.md`](../architecture/runtime-workflow.md) §3、§4。

---

## 2. 审查问题严重等级

| 等级 | 含义 |
|------|------|
| `CRITICAL` | 阻塞性问题，必须修复 |
| `HIGH` | 重要问题，必须修复 |
| `MEDIUM` | 改进建议，用户决定 |
| `LOW` | 可选建议 |

修订流程仅处理 CRITICAL 和 HIGH。

---

## 3. 审查问题分类

| 类别 | 适用范围 | 说明 |
|------|---------|------|
| `completeness` | 文档+代码 | 逻辑缺失、定义不全 |
| `correctness` | 代码 | 实现语义与 AC / 契约不符、算法 / 边界 / 状态转换错误 |
| `consistency` | 文档+代码 | 与上游 / 内部矛盾 |
| `convention` | 文档+代码 | 命名 / 格式 / 风格规范 |
| `security` | 文档+代码 | 安全漏洞、合规风险 |
| `feasibility` | 文档 | 技术可行性、实现性 |
| `ambiguity` | 文档 | 模糊不清、多义 |
| `structure` | 代码 | 架构 / 组织 / 职责划分 |
| `error-handling` | 代码 | 异常处理、边界条件 |
| `performance` | 代码 | 性能 / 效率 |
| `test-quality` | 代码 | 断言有效性、测试逻辑、边界覆盖 |
| `duplication` | 代码 | 跨文件 / 跨函数重复（Type-1/2 克隆） |
| `dead-code` | 代码 | 不可达分支、未引用的导出、永远为假的条件 |
| `complexity` | 代码 | 圈 / 认知复杂度过高、嵌套深度超阈值 |
| `coupling` | 代码 | 模块间引用过密、依赖图循环或扇出过大 |

权威清单见 [`.cataforge/rules/COMMON-RULES.md`](../../.cataforge/rules/COMMON-RULES.md) §统一问题分类体系；详见 [`../architecture/quality-and-learning.md`](../architecture/quality-and-learning.md)。

---

## 4. 文档引用格式

Agent 间通过标准化引用格式传递信息，避免全文复制：

```text
格式：{doc_id}#§{section_number}[.{item_id}]

示例：
  prd#§2.F-003      → PRD 文档第 2 节 Feature F-003
  arch#§3.M-auth    → 架构文档第 3 节 Module auth
  dev-plan#§3.T-005 → 开发计划第 3 节 Task T-005
```

`context` 的 navigate 分支负责按引用格式精准加载对应段落，降低 Agent 上下文占用。

---

## 5. 事件日志

所有关键事件记录到 `docs/EVENT-LOG.jsonl`（JSON Lines 格式）。`event` 枚举的权威来源是 [`.cataforge/schemas/event-log.schema.json`](../../.cataforge/schemas/event-log.schema.json)，共 16 个：

| 事件类型 | 含义 |
|---------|------|
| `session_start` / `session_end` | 会话开始 / 结束 |
| `phase_start` / `phase_end` | 阶段开始 / 结束 |
| `agent_dispatch` / `agent_return` | Agent 调度 / 返回 |
| `review_verdict` | 审查结论 |
| `user_decision` | 用户决策 |
| `revision_start` | 修订流程启动 |
| `tdd_phase` | TDD 阶段切换（RED / GREEN / REFACTOR） |
| `incident` | 异常 / 事故 |
| `state_change` | 状态变更 |
| `correction` | 用户纠正（触发 On-Correction Learning） |
| `doc_finalize` | 文档定稿落盘 |
| `sprint_complete` | sprint 全部任务卡审查通过（building 完成契约，`ref=dev-plan#sprint-N`） |
| `circuit_open` | 熔断信号（无进展 / 反复失败 / 达上限） |

示例事件（字段名 `event` 与 schema 对齐）：

```json
{"ts": "2026-04-16T08:00:00Z", "event": "phase_start", "phase": "development", "detail": "standard mode"}
{"ts": "2026-04-16T08:05:00Z", "event": "agent_dispatch", "phase": "development", "agent": "implementer", "ref": "dev-plan#§3.T-005", "detail": "GREEN"}
{"ts": "2026-04-16T08:30:00Z", "event": "review_verdict", "phase": "development", "status": "approved_with_notes", "detail": "2 notes"}
```

事件日志是 **不可变** 的，用于审计、回放、以及由 `reflector` Agent 生成跨项目经验。

---

## 6. CLI 退出码

| 退出码 | 含义 |
|-------|------|
| `0`  | 成功 |
| `1`  | 业务失败（如 `doctor` 发现 FAIL、缺 `.cataforge/`、配置错误） |
| `2`  | Click 用法错误（未知选项、缺必需参数等） |
| `3`  | KG 内容校验门失败（`kg import` / `kg validate` / `kg export` / `kg drift-check` doc↔store 漂移）— `KGVerificationError` |
| `6`  | SPARQL 查询超时（`kg query`）— `KGQueryTimeoutError` |
| `70` | 功能未实现（路线图 stub）— BSD sysexits `EX_SOFTWARE` |
| `127` | 审查 Skill 的 Layer 1 脚本不可执行 / 命令未找到 → FAIL（见 COMMON-RULES §Layer 1 调用协议；先跑 `cataforge doctor`） |

> `70` 选自 BSD sysexits.h `EX_SOFTWARE`，刻意避开 Click 自动使用的用法错误码 `2`。完整定义以 [`cli.md`](./cli.md) §退出码 为准；常量在 [`cataforge.interface.cli.errors`](../../src/cataforge/interface/cli/errors.py)。Layer 1 审查脚本的 `2` / `127` 失败语义见 [`.cataforge/rules/COMMON-RULES.md`](../../.cataforge/rules/COMMON-RULES.md) §Layer 1 调用协议。

---

## 参考

- 运行时协议：[`../architecture/runtime-workflow.md`](../architecture/runtime-workflow.md)
- 审查机制：[`../architecture/quality-and-learning.md`](../architecture/quality-and-learning.md)
- CLI 参考：[`cli.md`](./cli.md)
