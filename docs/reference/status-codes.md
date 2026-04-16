# 状态码与引用格式

> CataForge 运行时的统一状态码、文档引用格式、事件日志规范。

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

| 类别 | 说明 |
|------|------|
| `completeness` | 内容完整性 |
| `consistency` | 与上下游文档 / 代码的一致性 |
| `convention` | 命名 / 格式 / 编码规范 |
| `security` | 安全性问题 |
| `feasibility` | 技术可行性 |
| `ambiguity` | 表述模糊 |
| `structure` | 文档 / 代码结构 |
| `error-handling` | 错误处理 |
| `performance` | 性能相关 |

详见 [`../architecture/quality-and-learning.md`](../architecture/quality-and-learning.md)。

---

## 4. 文档引用格式

Agent 间通过标准化引用格式传递信息，避免全文复制：

```text
格式：{doc_id}#§{section_number}[.{item_id}]

示例：
  prd#§2.F-003      → PRD 文档第 2 节 Feature F-003
  arch#§3.M-auth    → 架构文档第 3 节 Module auth
  dev-plan#§1.T-005 → 开发计划第 1 节 Task T-005
```

`doc-nav` Skill 负责按引用格式精准加载对应段落，降低 Agent 上下文占用。

---

## 5. 事件日志

所有关键事件记录到 `docs/EVENT-LOG.jsonl`（JSON Lines 格式）：

| 事件类型 | 含义 |
|---------|------|
| `phase_start` / `phase_end` | 阶段开始 / 结束 |
| `review_verdict` | 审查结论 |
| `state_change` | 状态变更 |
| `agent_dispatch` | Agent 调度 |
| `correction` | 用户纠正（触发 On-Correction Learning） |

示例事件：

```json
{"ts": "2026-04-16T08:00:00Z", "type": "phase_start", "phase": "development", "mode": "standard"}
{"ts": "2026-04-16T08:05:00Z", "type": "agent_dispatch", "agent": "implementer", "task": "T-005"}
{"ts": "2026-04-16T08:30:00Z", "type": "review_verdict", "verdict": "approved_with_notes", "issues": 2}
```

事件日志是 **不可变** 的，用于审计、回放、以及由 `reflector` Agent 生成跨项目经验。

---

## 6. CLI 退出码

| 退出码 | 含义 |
|-------|------|
| `0` | 成功 |
| `1` | 业务失败（如 `doctor` 发现 FAIL） |
| `2` | Stub 子命令（v0.1.0 占位，v0.2+ 已实现） |

---

## 参考

- 运行时协议：[`../architecture/runtime-workflow.md`](../architecture/runtime-workflow.md)
- 审查机制：[`../architecture/quality-and-learning.md`](../architecture/quality-and-learning.md)
- CLI 参考：[`cli.md`](./cli.md)
