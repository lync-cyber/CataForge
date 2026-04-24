# TDD 工作流

> CataForge 在 **Development 阶段** 使用 TDD 引擎编排 RED→GREEN→REFACTOR 三阶段循环，按微任务逐个推进。
>
> 阈值由 `.cataforge/framework.json` 的 `constants.TDD_LIGHT_LOC_THRESHOLD`（默认 `50`，以 lines of code 计）和 `constants.SPRINT_REVIEW_MICRO_TASK_COUNT`（默认 `3`）控制。

<p align="center">
  <img src="../assets/tdd-engine.svg" alt="CataForge TDD 引擎流程" width="95%">
</p>

## 三阶段循环

| 阶段 | 负责 Agent | 目标 | 写入路径 |
|------|-----------|------|---------|
| **RED** | `test-writer` | 根据验收标准编写**失败**的测试用例（所有测试必须 FAIL） | `src/`, `tests/` |
| **GREEN** | `implementer` | 编写**最小实现**让测试通过 | `src/`, `tests/` |
| **REFACTOR** | `refactorer` | 在测试全绿的前提下优化代码质量 | `src/`, `tests/` |

> 若 REFACTOR 后测试失败，状态回滚为 `rolled-back`，保留 GREEN 阶段产出。

---

## 两种模式：standard vs light

| 模式 | 阶段 | 触发条件 |
|------|------|---------|
| **standard** | RED → GREEN → REFACTOR 三步 | 微任务 LOC ≥ `TDD_LIGHT_LOC_THRESHOLD`（默认 50） |
| **light** | RED+GREEN 合并 → REFACTOR | 微任务 LOC < 阈值 |

`tech-lead` 在任务分解阶段为每个微任务预判 LOC（lines of code，代码行数），落入 `dev-plan` 中；TDD 引擎按预判选择模式。

---

## Sprint Review 触发

每完成 `SPRINT_REVIEW_MICRO_TASK_COUNT` 个微任务（默认 3，见 `framework.json.constants`），`reviewer` 调用 `sprint-review` skill 审查 AC 覆盖率与范围偏移。详见 [`../architecture/quality-and-learning.md`](../architecture/quality-and-learning.md) §4。

---

## 微任务调度循环

```text
for each task in dev-plan:
    mode = LIGHT if task.loc < threshold else STANDARD

    if mode == STANDARD:
        test-writer  → produce failing tests  (RED)
        implementer  → make tests pass        (GREEN)
        refactorer   → optimize               (REFACTOR)
    else:
        implementer  → tests + code in one go (RED+GREEN)
        refactorer   → optimize               (REFACTOR)

    if completed_tasks % SPRINT_REVIEW_MICRO_TASK_COUNT == 0:
        reviewer → sprint-review
```

---

## 配置要点

`.cataforge/framework.json` 相关字段：

```json
{
  "constants": {
    "TDD_LIGHT_LOC_THRESHOLD": 50,
    "SPRINT_REVIEW_MICRO_TASK_COUNT": 3
  }
}
```

| 常量 | 作用 | 典型值 |
|------|------|-------|
| `TDD_LIGHT_LOC_THRESHOLD` | standard / light 切换阈值（LOC） | `50` |
| `SPRINT_REVIEW_MICRO_TASK_COUNT` | 每 N 个微任务触发一次 Sprint Review | `3` |

---

## 状态码

TDD 三阶段 Agent 返回的状态遵循统一规范 — 完整定义见 [`../reference/status-codes.md`](../reference/status-codes.md) §1。最常见的四个：`completed` / `needs_revision` / `rolled-back` / `needs_input`。

---

## 参考

- 整体执行模式（standard / agile-lite / agile-prototype）：[`execution-modes.md`](./execution-modes.md)
- 阶段执行与中断恢复协议：[`../architecture/runtime-workflow.md`](../architecture/runtime-workflow.md)
- 审查与学习系统：[`../architecture/quality-and-learning.md`](../architecture/quality-and-learning.md)
