---
name: task-decomp
description: "任务拆分 — 功能到任务的分解，确保粒度单一可控。"
argument-hint: "<ARCH文档路径或模块列表>"
suggested-tools: Read, Write, Edit, Grep
depends: [doc-gen, doc-nav, task-dep-analysis]
disable-model-invocation: false
user-invocable: true
---

# 任务拆分 (task-decomp)
## 能力边界
- 能做: 功能→任务分解、复杂度评级、Sprint划分、TDD验收标准定义
- 不做: 架构决策、代码实现、测试执行

## 输入规范
- ARCH模块划分(M-{NNN}) + 接口契约(API-{NNN})
- UI-SPEC组件(C-{NNN}) + 页面(P-{NNN})

## 输出规范
- 任务卡(T-{NNN})，每个包含:
  - 目标、模块、接口、复杂度(S/M/L)
  - tdd_acceptance: 验收标准映射
  - deliverables: 交付物文件清单
  - context_load: doc-nav加载清单
  - 实现提示(仅在必要时)
- Sprint划分表
- 依赖图 + 关键路径
- 集成/E2E测试规划: 按Sprint标注需验证的模块间交互和端到端用户流程

## 执行流程
1. 从ARCH模块和接口推导任务
2. 评估每个任务复杂度：跨越多个模块、或 context_load > 5 个章节、或步骤无法在单次 Agent 调用中枚举完整时，继续拆分
3. 定义tdd_acceptance(映射AC)
4. 定义deliverables(明确交付文件)
5. 定义context_load(doc-nav引用)
6. 建立依赖图: 调用 dep-analysis skill，脚本自动生成 Mermaid 依赖图并写入 dev-plan#§2
7. 按依赖关系划分Sprint(参考 dep-analysis 输出的 sprint_groups)

## 效率策略
- 先拆后排: 先拆任务再排依赖
- context_load精确到章节，避免全文加载
