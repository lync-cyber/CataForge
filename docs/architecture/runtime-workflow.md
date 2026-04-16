# 运行时工作流

> 本文描述 CataForge 在一次完整 SDLC 生命周期内的运行时行为：Bootstrap、阶段执行、TDD 编排、中断恢复、修订协议。

## 1. 项目初始化（Bootstrap）

当用户通过 `start-orchestrator` 技能启动项目，编排器执行：

```text
Step 1: 收集项目信息
    ├── 项目名称、技术栈
    ├── 命名规范、提交格式、分支策略
    └── 审查检查点选择

Step 2: 选择执行模式（standard / agile-lite / agile-prototype）

Step 3: 创建目录结构（按模式不同）

Step 4: 生成 CLAUDE.md（从 PROJECT-STATE.md 模板）

Step 5: 写入框架版本（来自 pyproject.toml）

Step 6: 选择目标平台（claude-code / cursor / codex / opencode）

Step 7: 填充执行环境，应用最小权限

Step 8: 创建 docs/NAV-INDEX.md

Step 9: 进入初始阶段
```

---

## 2. 阶段执行流程

无论 `standard` / `agile-lite` / `agile-prototype`，每个阶段都遵循统一的五段执行：

<p align="center">
  <img src="../assets/phase-execution.svg" alt="CataForge 阶段执行流程" width="80%">
</p>

出口分支：

- **approved** → 进入下一阶段
- **approved_with_notes** → 用户选择接受建议或修复
- **needs_revision** → 修订协议（见 §4）
- **needs_input** → 中断恢复协议（见 §3）

三种模式的完整阶段对比：[`../guide/execution-modes.md`](../guide/execution-modes.md)。

---

## 3. 中断恢复协议

当 Agent 返回 `needs_input` 状态时：

```text
1. 编排器暂停当前 Agent
2. 向用户展示问题（最多 MAX_QUESTIONS_PER_BATCH 个）
3. 用户回答后，以 task_type=continuation 重新调度 Agent
4. Agent 加载中间产出 → 应用用户回答 → 从恢复点继续
5. 同一 Agent 同一阶段最多 2 次中断恢复
6. 第 3 次中断请求人工介入
```

> 防止 Agent 陷入无限提问循环。超过阈值后必须由人类决定是简化需求还是切换策略。

---

## 4. 修订协议

当 Reviewer 返回 `needs_revision` 时：

```text
1. 编排器加载 REVIEW 报告
2. 以 task_type=revision 重新调度原 Agent
3. Agent 按 CRITICAL > HIGH > MEDIUM > LOW 排序问题
4. 仅修复 CRITICAL 和 HIGH 级别问题
5. 增量修正文档 / 代码（不重写全文）
6. 重新提交 Reviewer 审查
```

MEDIUM / LOW 级问题转为 `approved_with_notes` 提示，由用户决定是否处理。

---

## 5. TDD 编排（Development 阶段）

Development 阶段使用 TDD Engine 编排，按微任务逐个推进：

<p align="center">
  <img src="../assets/tdd-engine.svg" alt="CataForge TDD 引擎流程" width="95%">
</p>

- 每个微任务先由 LOC 判定走 `standard` 还是 `light`
- 完成若干微任务后触发 `Sprint Review`
- `REFACTOR` 阶段若测试失败，状态回滚为 `rolled-back`，保留 GREEN 阶段产出

详见 [`../guide/tdd-workflow.md`](../guide/tdd-workflow.md)。

---

## 6. 手动审查检查点

可配置的检查点，在阶段转换前暂停等待人工确认：

| 检查点 | 触发时机 |
|-------|---------|
| `phase_transition` | 每次阶段转换前暂停 |
| `pre_dev` | 进入开发阶段前暂停 |
| `pre_deploy` | 进入部署阶段前暂停 |
| `post_sprint` | 每个 Sprint 完成后暂停 |
| `none` | 不设检查点 |

**默认配置**：`["pre_dev", "pre_deploy"]`

配置位置：`.cataforge/framework.json` → `runtime.checkpoints`。

---

## 7. 事件日志

所有关键事件记录到 `docs/EVENT-LOG.jsonl`（JSON Lines）：

| 事件类型 | 含义 |
|---------|------|
| `phase_start` / `phase_end` | 阶段开始 / 结束 |
| `review_verdict` | 审查结论 |
| `state_change` | 状态变更 |
| `agent_dispatch` | Agent 调度 |
| `correction` | 用户纠正（触发 On-Correction Learning） |

事件日志是 **不可变的**，用于审计、回放、后续由 `reflector` Agent 生成跨项目经验。

---

## 参考

- 架构分层与模块职责：[`overview.md`](./overview.md)
- 平台适配与部署：[`platform-adaptation.md`](./platform-adaptation.md)
- 质量闸与学习系统：[`quality-and-learning.md`](./quality-and-learning.md)
- 状态码全集：[`../reference/status-codes.md`](../reference/status-codes.md)
