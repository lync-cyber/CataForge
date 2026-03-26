---
name: testing
description: "测试 — 测试策略规划、测试编写与执行、覆盖率分析、缺陷记录。"
argument-hint: "<操作: plan|write|execute|report> <测试类型: unit|integration|e2e|all>"
suggested-tools: Read, Write, Edit, Bash, Glob, Grep
depends: [doc-gen, doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 测试 (testing)

## 能力边界
- 能做: 测试策略规划、测试用例矩阵编写、Unit/Integration/E2E测试编写与执行、覆盖率分析、缺陷记录
- 不做: 源代码修改(仅编写测试)、架构变更

## 与tdd-engine的关系
- **tdd-engine(Phase 5)**: 开发阶段，为每个任务卡编写RED测试+GREEN实现，产出单元测试
- **testing(Phase 6)**: 测试阶段，补充集成测试/E2E测试、审查tdd-engine测试覆盖盲区、产出测试报告
- 两者独立运行，无依赖关系
- testing不重写tdd-engine已有测试，仅补充覆盖盲区(边界条件、异常路径、未覆盖分支)

## 输入规范
- dev-plan 任务列表和验收标准
- arch 接口契约
- ui-spec 交互流程(E2E测试时)
- 已有代码和单元测试(DEV阶段产出)

## 输出规范
- 测试策略(金字塔分层 + 覆盖率目标)
- 测试用例矩阵(TC-{NNN})
- 测试文件(单元/集成/E2E)
- 测试执行报告
- 缺陷清单(关联T-{NNN})

## 操作指令

### 指令1: 规划测试策略 (plan)
1. 分析dev-plan任务和arch接口，评估测试范围
2. 规划测试金字塔分层(Unit/Integration/E2E占比)
3. 编写测试用例矩阵(TC-{NNN})，与AC一一映射
4. 设定覆盖率目标(按模块)
5. 确定测试环境和工具链配置

### 指令2: 编写测试 (write)
按测试类型编写:

**Unit测试**:
- 输入: 任务卡验收标准 + 接口契约
- 范围: 函数/方法级，隔离外部依赖
- 工具: 按项目技术栈选择(pytest/jest/xunit等)
- 定位: 审查和补充 DEV 阶段 tdd-engine 产出的测试覆盖盲区(边界条件、异常路径、未覆盖分支)，而非重写已有测试。tdd-engine 与 testing skill 各自独立，无依赖关系。

**Integration测试**:
- 输入: arch接口契约 + 模块间依赖关系
- 范围: 模块间接口调用、数据流转
- 重点: API契约验证、数据库交互、IPC边界

**E2E测试**:
- 输入: ui-spec交互流程 + 核心用户路径
- 范围: 完整用户场景，端到端验证
- 工具: 按项目选择(Playwright/Cypress/Selenium等)

### 指令3: 执行测试 (execute)
1. 运行全部测试套件(或指定类型)
2. 收集测试结果和覆盖率数据
3. 记录失败用例和缺陷，关联任务ID(T-{NNN})
4. 缺陷即时归档，包含复现步骤和上下文

### 指令4: 产出报告 (report)
1. 汇总测试执行结果(通过/失败/跳过)
2. 覆盖率分析(对比目标)
3. 缺陷清单(严重等级 + 关联任务)
4. 结论与建议(是否达到发布标准)
5. 通过doc-gen填充test-report模板

## 效率策略
- 优先覆盖核心路径和模块接口
- 测试用例与AC一一映射，避免遗漏
- 集成测试优先覆盖模块间接口
- E2E测试聚焦核心用户路径，不追求全覆盖
- 缺陷即时归档，关联上下文
