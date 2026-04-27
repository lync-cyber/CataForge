---

## name: tdd-engine
description: "TDD引擎 — 编排RED→GREEN→REFACTOR三阶段子代理执行TDD开发，支持 light/standard/prototype-inline 三档与 sprint 内独立任务并行调度。"
argument-hint: "<任务卡ID如T-001>"
suggested-tools: file_read, file_write, file_edit, shell_exec, file_glob, file_grep, agent_dispatch
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true

# TDD引擎 (tdd-engine)

## 能力边界

- 能做: 指导orchestrator编排TDD三阶段子代理(RED/GREEN/REFACTOR)、light/standard 档位路由、prototype 主线程内联实现、同 sprint_group 独立任务并行调度、定义子代理prompt模板、任务上下文 bundle 缓存
- 不做: 需求分析、架构设计、文档生成

## 架构说明

orchestrator作为主线程Agent，在Phase 5逐任务执行时调用本skill。每个TDD阶段作为独立子代理启动，拥有独立上下文窗口，避免阶段间上下文污染。

```
orchestrator (主线程)
  ├─ 通过调度接口启动 → RED SubAgent (test-writer) — 独立上下文
  ├─ 收集RED产出 → 通过调度接口启动 → GREEN SubAgent (implementer) — 独立上下文
  ├─ （可选）GREEN 后 code-review Layer 1 命中 `TDD_REFACTOR_TRIGGER` → REFACTOR SubAgent (refactorer)
  └─ 汇总产出 → 更新dev-plan任务状态
```

light 模式合并 RED+GREEN 为单次 implementer 调用；agile-prototype 模式 implementer 在主线程内联运行（不再 dispatch 子代理）。

## TDD 子代理共享约束

以下约束适用于所有 TDD 子代理，通过 AGENT.md 的 disallowedTools 和本节定义：

- AskUserQuestion 不可用。如需用户输入，返回 blocked 并在 `<questions>` 描述问题，orchestrator 以 continuation 重启
- 返回 `<agent-result>` 格式（详见 dispatch-prompt.md §COMMON-SECTIONS）
- blocked 时可追加 `<questions>` 字段

## 输入规范

- dev-plan#T-xxx任务卡(含tdd_acceptance, deliverables, context_load, 可选 task_kind/tdd_mode/tdd_refactor/security_sensitive)
- 通过doc-nav加载的arch相关章节(接口契约、数据模型、目录结构、命名规范)

## 阶段间传递格式

子代理间通过文件系统传递状态：Step 1 产出**任务上下文 bundle**（见 §Step 1），后续阶段子代理 prompt 仅传 bundle 路径 + 上一阶段产出路径，子代理一次 Read 替代 prompt 内联：

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

orchestrator按以下步骤编排每个任务(T-xxx)的TDD。

**任务路由分支**: 读取任务卡 `task_kind` 和 `tdd_mode` 字段:

- `task_kind` ∈ `CODE_REVIEW_L2_SKIP_TASK_KINDS`（默认 `[chore, config, docs]`）→ **跳过 TDD**，由 implementer 单次调用直接产出 + lint hook 兜底，进入 Step 5
- `tdd_mode` 缺省（缺省视为 `TDD_DEFAULT_MODE` = `light`）:
  - `light` → Step 1 → **Step 2+3 合并** (见 §Light 模式) → Step 4 按条件 → Step 5
  - `standard` → Step 1 → Step 2 (RED) → Step 3 (GREEN) → Step 4 按条件 → Step 5
- 执行模式为 `agile-prototype` → 走 §Prototype Inline 模式（implementer 主线程内联，不 dispatch）

**REFACTOR 条件触发**: 任务卡显式 `tdd_refactor: required` 强制触发；否则在 GREEN 后跑一次 code-review Layer 1（lint + 腐化探针），结果命中 `TDD_REFACTOR_TRIGGER`（默认 `[complexity, duplication, coupling]`）任一 category 才调度 refactorer。

### Step 1: 准备上下文 + 写入任务 bundle

通过doc-nav加载任务卡的context_load章节，提取:

- 验收标准(tdd_acceptance → AC列表)
- 接口契约(arch#API-xxx)
- 目录结构和命名规范(arch#§6, arch#§7)
- deliverables清单
- 任务卡字段：`task_kind`、`tdd_mode`、`tdd_refactor`、`security_sensitive`

orchestrator 把以上内容拼装为单文件 `.cataforge/.cache/tdd/T-{xxx}-context.md`（首次创建即写）。后续子代理 prompt 仅传 bundle 路径，子代理一次 Read 即可获得全部上下文，避免每阶段 prompt 重复内联 arch 摘要导致的 token 浪费。

bundle 文件结构（固定章节顺序）:

```
# Task Context Bundle: T-{xxx}

## meta
- task_kind: {feature|fix|chore|config|docs}
- tdd_mode: {light|standard}
- tdd_refactor: {auto|required|skip}
- security_sensitive: {true|false}

## tdd_acceptance
- AC-001: ...
- AC-002: ...

## interface_contract
{arch 接口定义片段}

## directory_layout
{arch#§6 摘要}

## naming_convention
{arch#§7 摘要}

## deliverables
- ...

## test_command
{按技术栈，如 `pytest -q --tb=short tests/`}
```

bundle 在任务完成（Step 5）后保留以供 sprint-review 引用，下一个 sprint 再清理。

### Step 2: RED Phase — 启动test-writer子代理

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD RED: {T-xxx}"`

通过调度接口启动。角色定义、返回格式和异常处理已在 test-writer AGENT.md 中定义，通过 subagent_type 自动加载，prompt 仅需传任务 bundle 路径:

```
调度请求:
  agent_id: "test-writer"
  description: "TDD RED: T-xxx 编写失败测试"
  prompt: |
    当前项目: {项目名}。
    任务上下文 bundle: .cataforge/.cache/tdd/T-{xxx}-context.md（请先 Read 该文件获取 AC / 接口契约 / 目录结构 / test_command）

    任务: 为 bundle 中 §tdd_acceptance 的所有 AC 编写测试用例，确保所有新增测试 FAIL。
```

> **同模块 RED 批量化** (§C2): 当 orchestrator 一次性派发同 sprint_group 内同模块（context_load 共享 ≥1 个 arch#§2.M-xxx）的 N 个任务时，可合并为**一次 test-writer 调用**，prompt 列出所有任务 bundle 路径，summary 按 task_id 分块返回。失败归因通过 bundle 路径反推。仅适用于任务数 ≤ 4 且共享同一模块；否则回退到逐任务调度。

验证（orchestrator 执行）:

1. 确认新增测试均为 FAILED。标记为"pre-existing"的 PASSED 测试不视为异常。
2. summary 中如有 SyntaxError / 配置错误等异常，要求 test-writer 以 continuation 模式修正（最多 1 次，仍异常则 blocked 请求人工介入）。

  > 失败原因验证和断言有效性已由 test-writer 的 Execution Rules 完成；orchestrator 不再做 summary 字段级二次核验，避免主线程上下文重复消费 test-writer 详细输出。

### Step 3: GREEN Phase — 启动implementer子代理

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD GREEN: {T-xxx}"`

通过调度接口启动。角色定义、返回格式和异常处理已在 implementer AGENT.md 中定义，通过 subagent_type 自动加载:

```
调度请求:
  agent_id: "implementer"
  description: "TDD GREEN: T-xxx 最小实现"
  prompt: |
    当前项目: {项目名}。
    任务上下文 bundle: .cataforge/.cache/tdd/T-{xxx}-context.md
    RED 阶段产出 test_files: {RED 阶段返回的路径列表}

    任务: 编写最小代码使所有测试通过。
```

验证: 确认返回的 test-result 全部 PASSED。

### Step 4: REFACTOR Phase — 条件触发 (可选)

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD REFACTOR: {T-xxx}"`（仅在实际触发时记录）

**触发判定** (orchestrator 在 GREEN 完成后执行):

1. 任务卡 `tdd_refactor: required` → 强制触发
2. 任务卡 `tdd_refactor: skip` → 直接跳过进入 Step 5
3. 缺省 → 对 GREEN 产出的 impl_files 跑 `cataforge skill run code-review -- {impl_files} --focus complexity,duplication,coupling`（Layer 1 only，不调 Layer 2）：
   - Layer 1 输出包含 `TDD_REFACTOR_TRIGGER` 任一 category 的 finding → 触发
   - 否则跳过

触发后通过调度接口启动:

```
调度请求:
  agent_id: "refactorer"
  description: "TDD REFACTOR: T-xxx 代码优化"
  prompt: |
    当前项目: {项目名}。
    任务上下文 bundle: .cataforge/.cache/tdd/T-{xxx}-context.md
    实现文件: {GREEN阶段产出的impl_files}
    测试文件: {RED阶段产出的test_files}
    触发原因: code-review Layer 1 命中 {category 列表}（请重点优化对应维度）

    任务: 优化代码质量，保持所有测试通过。
```

跳过 REFACTOR 时不记录 tdd_phase REFACTOR 事件，仅在 Step 5 汇总中标注 "REFACTOR skipped (no trigger)"。

### Light 模式: 合并 RED+GREEN (tdd_mode=light)

`tdd_mode=light` 任务（默认；LOC ≤ `TDD_LIGHT_LOC_THRESHOLD` 时 tech-lead 标记，缺省也视为 light）将 Step 2 和 Step 3 合并为一次 implementer 子代理调用，子代理内部先写 AC 对应的失败测试再补最小实现。

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD LIGHT: {T-xxx}"`

通过调度接口启动:

```
调度请求:
  agent_id: "implementer"
  description: "TDD LIGHT: T-xxx 合并RED+GREEN"
  prompt: |
    当前项目: {项目名}。
    模式: tdd_mode=light（合并 RED+GREEN）
    任务上下文 bundle: .cataforge/.cache/tdd/T-{xxx}-context.md（请先 Read 该文件）

    任务: 先为 bundle 中 §tdd_acceptance 的每条 AC 写一份失败测试，确认 FAIL 后再补最小实现使测试通过。

    === 输出要求 ===
    在 <agent-result>.outputs 中同时返回:
      - test_files: [...]
      - impl_files: [...]
    summary 中标注: "light mode — RED+GREEN 合并，最终测试全部 PASSED"
```

验证（orchestrator 执行）:

1. 确认 outputs 同时含 test_files 和 impl_files
2. 运行测试确认最终全部 PASSED
3. REFACTOR 处理：按 §Step 4 条件触发判定执行（agile-prototype 强制跳过；agile-lite 仅在 code-review Layer 1 命中 `TDD_REFACTOR_TRIGGER` 时才触发）

### Prototype Inline 模式 (执行模式 = agile-prototype)

agile-prototype 项目的任务全部走 implementer **主线程内联**，不通过 agent_dispatch 启动子代理：

- orchestrator 自身在主线程加载 brief.md §5 任务卡和 bundle，按 light 模式的"先测试后实现"步骤直接产出 test_files + impl_files
- 跳过 Step 4 REFACTOR
- 跳过 per-task code-review（lint hook 已兜底；prototype 不进 sprint-review）
- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD PROTOTYPE-INLINE: {T-xxx}"`

收益：节省一次子代理 boot（AGENT.md + COMMON-RULES + dispatch-prompt 模板加载约 3-5K token）。

### Step 5: 汇总与状态更新

orchestrator完成以下收尾:

1. 验证最终测试结果(运行测试确认全部PASS)
2. 核对deliverables清单(所有文件已创建)
3. 触发代码审查时，审查范围包含 impl_files 和 test_files（测试代码质量纳入 code-review Layer 2）；按 code-review §Layer 2 短路条件判断是否仅跑 Layer 1
4. 通过doc-gen(write-section)将dev-plan#§1对应任务行状态更新为done
5. 如 blocked 且含 questions → 按 ORCHESTRATOR-PROTOCOLS.md §TDD Blocked Recovery Protocol 处理
6. 如 blocked 且无 questions → 记录原因并请求人工介入

> **Sprint级审查**: 当Sprint内所有任务完成Step 5后，orchestrator触发sprint-review skill执行Sprint完成度审查（见 ORCHESTRATOR-PROTOCOLS.md §Sprint Review Protocol）。Sprint审查在所有任务的code-review之后、下一Sprint开始之前执行。

## 效率策略

- 每个子代理拥有独立上下文，避免阶段间污染
- 子代理间仅传递文件路径，非代码全文
- 按context_load加载最小必要上下文
- **任务 bundle 一次写多次读**：Step 1 写 `.cataforge/.cache/tdd/T-{xxx}-context.md`，后续阶段子代理 prompt 不再内联 arch 摘要，节省每次调度 prompt 体积
- **light 默认 + REFACTOR 条件触发**：典型小任务从 3 次子代理调度收敛到 1 次
- **prototype 主线程内联**：原型项目省下 implementer 子代理 boot 开销
- **同模块 RED 批量化**：sprint_group 内任务共享模块时，test-writer 一次写完多任务测试，减少子代理 boot 次数
