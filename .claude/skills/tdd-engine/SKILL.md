---
name: tdd-engine
description: "TDD引擎 — 编排RED→GREEN→REFACTOR三阶段子代理执行TDD开发。"
argument-hint: "<任务卡ID如T-001>"
suggested-tools: Read, Write, Edit, Bash, Glob, Grep, Agent
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# TDD引擎 (tdd-engine)

## 能力边界
- 能做: 指导orchestrator编排TDD三阶段子代理(RED/GREEN/REFACTOR)、定义子代理prompt模板、验证阶段间传递
- 不做: 需求分析、架构设计、文档生成

## 架构说明
orchestrator作为主线程Agent，在Phase 5逐任务执行时调用本skill。每个TDD阶段作为独立子代理启动，拥有独立上下文窗口，避免阶段间上下文污染。

```
orchestrator (主线程)
  ├─ 通过Agent tool启动 → RED SubAgent (test-writer) — 独立上下文
  ├─ 收集RED产出 → 通过Agent tool启动 → GREEN SubAgent (implementer) — 独立上下文
  ├─ 收集GREEN产出 → 通过Agent tool启动 → REFACTOR SubAgent (refactorer) — 独立上下文
  └─ 汇总产出 → 更新dev-plan任务状态
```

## 输入规范
- dev-plan#T-xxx任务卡(含tdd_acceptance, deliverables, context_load)
- 通过doc-nav加载的arch相关章节(接口契约、数据模型、目录结构、命名规范)

## 阶段间传递格式
子代理间通过文件系统传递状态，orchestrator在prompt中传入上一阶段产出路径:

```
RED → GREEN:
  从RED的<agent-result>提取:
  - outputs → test_files路径列表
  - summary → 测试结果(N FAILED, M PASSED)

GREEN → REFACTOR:
  从GREEN的<agent-result>提取:
  - outputs → impl_files路径列表
  合并RED阶段的test_files一并传入

REFACTOR → orchestrator:
  从REFACTOR的<agent-result>提取:
  - outputs → 最终文件路径列表
  - summary → 测试结果 + 重构变更摘要
```

## 执行流程

orchestrator按以下步骤编排每个任务(T-xxx)的TDD:

### Step 1: 准备上下文
通过doc-nav加载任务卡的context_load章节，提取:
- 验收标准(tdd_acceptance → AC列表)
- 接口契约(arch#API-xxx)
- 目录结构和命名规范(arch#§6, arch#§7)
- deliverables清单

**变量绑定**: 以上提取的具体内容在 Step 2-4 的子代理 prompt 中替换对应 `{占位符}`，确保每个子代理收到完整的上下文而无需自行读取文件。

### Step 2: RED Phase — 启动test-writer子代理
使用Agent tool启动。角色定义、返回格式和异常处理已在 test-writer AGENT.md 中定义，通过 subagent_type 自动加载，prompt 仅需传入任务信息:
```
Agent tool:
  subagent_type: "test-writer"
  description: "TDD RED: T-xxx 编写失败测试"
  prompt: |
    当前项目: {项目名}。

    === 任务信息 ===
    任务: 为以下验收标准编写测试用例，确保所有新增测试FAIL。
    验收标准: {tdd_acceptance列表}
    接口契约: {arch接口定义}
    测试框架: {按技术栈}
    目录结构: {arch#§6}
```

验证: 确认新增测试均为FAILED。标记为"pre-existing"的PASSED测试不视为异常。

### Step 3: GREEN Phase — 启动implementer子代理
使用Agent tool启动。角色定义、返回格式和异常处理已在 implementer AGENT.md 中定义，通过 subagent_type 自动加载:
```
Agent tool:
  subagent_type: "implementer"
  description: "TDD GREEN: T-xxx 最小实现"
  prompt: |
    当前项目: {项目名}。

    === 任务信息 ===
    任务: 编写最小代码使所有测试通过。
    测试文件: {RED阶段产出的test_files}
    接口契约: {arch接口定义}
    目录结构: {arch#§6}
    命名规范: {arch#§7}
```

验证: 确认返回的test-result全部PASSED。

### Step 4: REFACTOR Phase — 启动refactorer子代理
使用Agent tool启动。角色定义、返回格式和异常处理已在 refactorer AGENT.md 中定义，通过 subagent_type 自动加载:
```
Agent tool:
  subagent_type: "refactorer"
  description: "TDD REFACTOR: T-xxx 代码优化"
  prompt: |
    当前项目: {项目名}。

    === 任务信息 ===
    任务: 优化代码质量，保持所有测试通过。
    实现文件: {GREEN阶段产出的impl_files}
    测试文件: {RED阶段产出的test_files}
    命名规范: {arch#§7}
```

### Step 5: 汇总与状态更新
orchestrator完成以下收尾:
1. 验证最终测试结果(运行测试确认全部PASS)
2. 核对deliverables清单(所有文件已创建)
3. 通过doc-gen(write-section)将dev-plan#§1对应任务行状态更新为done
4. 如 blocked 且含 questions → 按 ORCHESTRATOR-PROTOCOLS.md §TDD Blocked Recovery Protocol 处理
5. 如 blocked 且无 questions → 记录原因并请求人工介入

> **Sprint级审查**: 当Sprint内所有任务完成Step 5后，orchestrator触发sprint-review skill执行Sprint完成度审查（见 ORCHESTRATOR-PROTOCOLS.md §Sprint Review Protocol）。Sprint审查在所有任务的code-review之后、下一Sprint开始之前执行。

## 效率策略
- 每个子代理拥有独立上下文，避免阶段间污染
- 子代理间仅传递文件路径，非代码全文
- 按context_load加载最小必要上下文
- 子代理prompt中内联必要的arch约束，避免子代理再读取文件
