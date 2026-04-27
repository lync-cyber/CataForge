<!-- 变更原因：原文档只有伪代码缺端到端真实示例；补一个最小示例 + 边界情况；修正"若干"等模糊量词 -->
# TDD 工作流

CataForge 在 Development 阶段用 TDD 引擎按微任务推进 RED → GREEN → REFACTOR 三阶段循环。

阈值由 `.cataforge/framework.json` 的 `constants` 段控制：

- `TDD_LIGHT_LOC_THRESHOLD`（默认 `50`）— LOC 低于此值走 light（RED+GREEN 合并）
- `SPRINT_REVIEW_MICRO_TASK_COUNT`（默认 `3`）— 每 N 个微任务触发一次 Sprint Review

<div align="center">
  <img src="../assets/tdd-engine.svg" alt="RED → GREEN → REFACTOR 三阶段循环，按微任务 LOC 选 standard 或 light" width="95%">
</div>

## 三阶段做什么

| 阶段 | 负责 Agent | 目标 | 写入 |
|------|-----------|------|------|
| **RED** | `test-writer` | 编写失败的测试用例（必须 FAIL） | `tests/` |
| **GREEN** | `implementer` | 编写最小实现让测试转绿 | `src/`、`tests/` |
| **REFACTOR** | `refactorer` | 在测试全绿前提下优化代码 | `src/`、`tests/` |

REFACTOR 失败时状态回滚为 `rolled-back`，保留 GREEN 阶段产出，REFACTOR 改动作废。

## standard 与 light 何时切换

| 模式 | 阶段顺序 | 触发 |
|------|---------|------|
| **standard** | RED → GREEN → REFACTOR | 微任务 LOC ≥ `TDD_LIGHT_LOC_THRESHOLD`（默认 50） |
| **light** | RED+GREEN 合并 → REFACTOR | 微任务 LOC < 阈值 |

`tech-lead` 在 dev-plan 阶段为每个微任务预判 LOC，TDD 引擎按预判选模式。

## 端到端示例 · 一个微任务

<!-- 变更原因：补可运行示例，原文档没有 -->

假设 `dev-plan` 中有一项微任务：

```yaml
# docs/dev-plan.md 摘录
T-005:
  title: "为 ConfigManager.load 加 schema 校验"
  loc_estimate: 80           # ≥ 50 → 走 standard
  acceptance_criteria:
    - "未知 key 抛 ConfigSchemaError"
    - "缺必填字段抛 ConfigSchemaError"
    - "合法配置返回 Config 实例"
```

引擎依次调度三个 Agent：

```text
1. test-writer (RED)
   → 在 tests/core/test_config_loader.py 写 3 个测试，全 FAIL
   → 状态：completed，移交 GREEN

2. implementer (GREEN)
   → 在 src/cataforge/core/config.py 改 load(),
     最小实现让 3 个测试通过
   → 状态：completed，移交 REFACTOR

3. refactorer (REFACTOR)
   → 把校验逻辑抽到 _validate_schema()，无新行为
   → 跑全量 pytest 通过
   → 状态：completed
```

每个阶段都会向 `docs/EVENT-LOG.jsonl` 追加 `agent_dispatch` 与 `phase_end` 事件。

## 边界情况

### REFACTOR 后测试红了

```text
3'. refactorer (REFACTOR)
    → pytest 报 1 失败
    → 引擎丢弃 REFACTOR 阶段的代码改动
    → 状态：rolled-back
    → 保留 GREEN 产出，记入 EVENT-LOG 供 reflector 分析
```

### light 模式（微任务 LOC = 20）

```text
1. implementer (RED+GREEN 合并)
   → 一次性写测试 + 实现
2. refactorer (REFACTOR)
   → 同上
```

### 反例 — 不要在 dev-plan 里写 `loc_estimate: 0`

`tech-lead` 必须给非零估算。0 会让引擎降级到 light 但实际 LOC 远超阈值，REFACTOR 阶段拿不到独立的 GREEN 状态供回滚。

## Sprint Review 触发

每完成 `SPRINT_REVIEW_MICRO_TASK_COUNT`（默认 3）个微任务，`reviewer` 调 `sprint-review` skill 审查 AC 覆盖率与范围偏移。详见 [`../architecture/quality-and-learning.md`](../architecture/quality-and-learning.md) §4。

## 配置

```json
{
  "constants": {
    "TDD_LIGHT_LOC_THRESHOLD": 50,
    "SPRINT_REVIEW_MICRO_TASK_COUNT": 3
  }
}
```

## 状态码

TDD 三阶段返回的状态码定义见 [`../reference/status-codes.md`](../reference/status-codes.md) §1。最常见四个：`completed` / `needs_revision` / `rolled-back` / `needs_input`。

## 参考

- 整体执行模式：[`execution-modes.md`](./execution-modes.md)
- 阶段执行与中断恢复：[`../architecture/runtime-workflow.md`](../architecture/runtime-workflow.md)
- 审查与学习系统：[`../architecture/quality-and-learning.md`](../architecture/quality-and-learning.md)
