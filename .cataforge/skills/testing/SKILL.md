---
name: testing
description: "测试 — 测试策略规划、测试编写与执行、覆盖率分析、缺陷记录。当需要规划测试策略、编写或执行测试套件、分析覆盖率或记录缺陷时使用。本 skill 不改源码（缺陷修复由 debug 负责），单任务 RED/GREEN 单元测试由 tdd-engine 负责，testing 聚焦集成/E2E 与覆盖盲区补充。"
argument-hint: "<操作: plan|write|execute|report> <测试类型: unit|integration|e2e|all>"
suggested-tools: Read, Write, Edit, Bash, Glob, Grep
depends: [context]
disable-model-invocation: false
user-invocable: true
---

# 测试 (testing)

## 能力边界
- 能做: 测试策略规划、测试用例矩阵编写、Unit/Integration/E2E测试编写与执行、覆盖率分析、缺陷记录
- 不做: 源代码修改 / 缺陷修复(由 debug 负责，testing 仅编写测试)、架构变更

## 与tdd-engine的关系
- **tdd-engine(Phase 5)**: 开发阶段，为每个任务卡编写RED测试+GREEN实现，产出单元测试
- **testing(Phase 6)**: 测试阶段，补充集成测试/E2E测试、审查tdd-engine测试覆盖盲区、产出测试报告
- 两者独立运行，无依赖关系
- testing不重写tdd-engine已有测试，仅补充覆盖盲区(边界条件、异常路径、未覆盖分支)

## 与debug的关系
- testing 输出"缺陷清单"后，由 orchestrator 调度 debug skill 接管根因定位与最小修复（testing 本身不改源码）
- debug 修复完成后由 testing 重跑相关用例验证；debug 内部已含回归验证步骤，testing 在缺陷清单上标 closed
- testing 仅记录现象 / 复现步骤 / 关联任务 ID，不替代 debug 的根因分析

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
- 范围: 仅补充 tdd-engine 未覆盖的函数/方法级盲区（边界条件 / 异常路径 / 未覆盖分支），隔离外部依赖，不重写已有单测
- 工具: 按项目技术栈选择(pytest/jest/xunit等)
- 定位: 补充 DEV 阶段覆盖盲区（见 §与tdd-engine的关系）

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
5. 通过context填充test-report模板

## Layer 1 检查项 (e2e_backdoor_scan)

> 权威清单见 `cataforge.runtime.skill.builtins.testing.CHECKS_MANIFEST`（framework-review 自动对账，本段与 manifest 不一致即 FAIL）。

- e2e 后门正则扫描 (tests/e2e/**) — 默认覆盖 .js/.ts/.jsx/.tsx + .py；命中 `window\.__\w+__\s*=` / `\?e2e=1` / `setStore\(.*JSON\.parse` 等模式即 WARN
- 真实输入路径声明 — e2e 套件至少含一处 `keyboard.type` / `page.fill` / `send_keys` 等真实交互调用，无任何 → WARN（提示套件可能纯 fixture 注入）

调用：`cataforge skill run testing -- scan-e2e tests/e2e/`，返回码语义按 §Layer 1 调用协议。

### Plugin-style rules (per-language extension)

后门 + 真实输入正则按语言拆到 YAML：

- 默认（cataforge package）：`cataforge.runtime.skill.builtins.testing.rules.e2e-{lang}.yaml`
- 项目 override（opt-in）：`<project>/.cataforge/skills/testing/rules/e2e-{lang}.yaml`

加新语言：在项目 `rules/` 放 `e2e-csharp.yaml` 等；schema 必填 `schema_version: 1` / `rule_type: e2e` / `language` / `extensions` + `backdoor_patterns`（每条需 `label`）/ `real_input_patterns`。framework-review B3-β 自动校验。

## Anti-Patterns

- 禁止：e2e 通过 `window.__*__` / `?e2e=1` / `?test=1` 后门或守门绕过真实用户输入路径；e2e 必须 ≥1 次真实浏览器交互（`keyboard.type` / `page.click` 等）作为 verdict=approved 前置条件
- 禁止：直接调用 store action / `setState` / `setAst(JSON.parse(...))` 等注入预构造数据替代真实输入路径 — 编辑器/表单/路由的 wiring 链路必须由测试照过
- 禁止：把"沙盒不可达 → CI 兜底"作为 verdict=conditional_release 的放行理由 —— `conditional_release` 必须显式声明 `blocking_conditions: []`，未消除前 Phase Transition 不能推进（详见 §Verdict 判定语义对应 qa-engineer/AGENT.md）
- 避免：单元测试用 `vi.mock` / `jest.mock` 全 stub 替换被测包的顶层导出，导致接口契约未真实验证（sprint-review `ac-coverage` 维度会复核）

## 效率策略
- 优先覆盖核心路径和模块接口
- 测试用例与AC一一映射，避免遗漏
- 集成测试优先覆盖模块间接口
- E2E测试聚焦核心用户路径，不追求全覆盖
- 缺陷即时归档，关联上下文
