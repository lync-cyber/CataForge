---
name: task-decomp
description: "任务拆分 — 功能到任务的分解，确保粒度单一可控。当 ARCH 完成、需要拆解任务卡、划分 Sprint 或定义 TDD 验收标准时使用。"
argument-hint: "<ARCH文档路径或模块列表>"
suggested-tools: Read, Write, Edit, Grep
depends: [context, task-dep-analysis]
disable-model-invocation: false
user-invocable: true
---

# 任务拆分 (task-decomp)
## 能力边界
- 能做: 功能→任务分解、复杂度评级、Sprint 初步划分、TDD 验收标准定义
- 不做: 架构决策、代码实现、测试执行、最终 Sprint 分组判定（依赖关系由 task-dep-analysis 计算并给出权威建议）

## 输入规范
- ARCH模块划分(M-{NNN}) + 接口契约(API-{NNN})
- UI-SPEC组件(UC-{NNN}) + 页面(P-{NNN})

## 输出规范
- 任务卡(T-{NNN})，每个包含:
  - 目标、模块、接口、复杂度(S/M/L)
  - tdd_acceptance: 验收标准映射（每条 AC 采用 Given-When-Then 格式，Then 子句必须包含可断言的具体值或约束）
  - deliverables: 交付物文件清单
  - context_load: context加载清单
  - 实现提示(仅在必要时)
- Sprint划分表
- 依赖图 + 关键路径
- 集成/E2E测试规划: 按Sprint标注需验证的模块间交互和端到端用户流程

## 执行流程
1. 从ARCH模块和接口推导任务
2. 评估每个任务复杂度：跨越多个模块、或 context_load > 5 个章节、或步骤无法在单次 Agent 调用中枚举完整时，继续拆分
3. 定义tdd_acceptance(映射AC)。每条 AC 采用 Given-When-Then 格式：
   - Given: 前置条件（输入数据、系统状态）
   - When: 触发动作（调用方法、发送请求、用户操作）
   - Then: 可观测结果（具体返回值/字段、状态变化、错误类型+消息）
   - Then 子句必须包含可断言的具体值或约束，禁止"实现 X"、"支持 Y"等无行为描述
4. 定义deliverables(明确交付文件)
5. 定义context_load(context引用)
6. 建立依赖图: 调用 task-dep-analysis skill，脚本自动生成 Mermaid 依赖图并写入 dev-plan#§2
7. 按依赖关系划分Sprint(参考 task-dep-analysis 输出的 sprint_groups)，遵循 MVP 切分原则:
   - 每个 Sprint 的产出应包含至少一个用户可感知的完整功能
   - 优先安排用户核心路径（`user_facing_critical_path: true`）的任务到前几个 Sprint
   - Sprint 1 例外: 基础设施任务允许集中在首个 Sprint，不要求用户可感知功能
   - 纯后端服务项目无此约束
8. 插入验证任务: 每个包含 `user_facing_critical_path: true` 任务的 Sprint 末尾，追加一个 `task_kind: validation` 的验证任务。验证任务不产出代码，orchestrator 遇到时暂停并向用户展示验证清单

## Anti-Patterns
- 禁止: 单任务预估 LOC > 250 或 AC > 6 条而不拆 —— 超此尺寸 implementer / test-writer 大概率触发 mid-progress drop，应在 task-decomp 阶段先拆
- 禁止: 把"重构 X"作为独立任务 —— 重构是 TDD REFACTOR 阶段的自然产物，独立 T-xxx 会让重构脱离测试安全网
- 禁止: deliverables 仅写 "实现 X 功能" 而不具体到文件路径 —— sprint-review 无法验证 AC 是否落到声明文件，验收形同虚设
- 避免: 任务横跨 ≥3 个 `arch#§2.M-xxx` —— 跨模块任务在 task-dep-analysis 输出中容易触发环依赖
- 禁止: AC 仅描述"实现 X 功能"/"支持 Y 格式"而无 Given-When-Then 行为描述 —— 模糊 AC 导致 test-writer 退化为存在性检查，无法推导断言期望值
- 禁止: Sprint 内全部为后端任务而无任何用户可感知的功能交付（Sprint 1 例外），除非项目为纯后端服务

## 效率策略
- 先拆后排: 先拆任务再排依赖
- context_load精确到章节，避免全文加载
