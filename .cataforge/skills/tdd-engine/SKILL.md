---
name: tdd-engine
description: "TDD引擎 — 编排RED→GREEN→REFACTOR三阶段子代理执行TDD开发，支持 light-dispatch / light-inline / standard / prototype-inline 四档与 sprint 内独立任务并行调度。"
argument-hint: "<任务卡ID如T-001>"
suggested-tools: file_read, file_write, file_edit, shell_exec, file_glob, file_grep, agent_dispatch
depends: [doc-nav]
disable-model-invocation: false
user-invocable: true
---

# TDD引擎 (tdd-engine)

## 能力边界

- 能做: 指导orchestrator编排TDD三阶段子代理(RED/GREEN/REFACTOR)、light-dispatch/light-inline/standard 档位路由、prototype 主线程内联实现、同 sprint_group 独立任务并行调度、定义子代理prompt模板
- 不做: 需求分析、架构设计、文档生成

## 架构说明

orchestrator作为主线程Agent，在Phase 5逐任务执行时调用本skill。每个TDD阶段作为独立子代理启动，拥有独立上下文窗口，避免阶段间上下文污染。

```
orchestrator (主线程)
  ├─ 通过调度接口启动 → RED SubAgent (test-writer) — 独立上下文
  ├─ 收集RED产出 → 通过调度接口启动 → GREEN SubAgent (implementer) — 独立上下文
  ├─ implementer self-report `refactor_needed=true` 或 `tdd_refactor: required` → REFACTOR SubAgent (refactorer)
  └─ 汇总产出 → 更新dev-plan任务状态
```

四档执行模式：

| 档 | 触发条件 | 执行位置 |
|---|---------|---------|
| **standard** | `tdd_mode=standard` | RED + GREEN + REFACTOR(条件) 三次 dispatch |
| **light-dispatch** | `tdd_mode=light` 且不满足 inline 条件 | implementer 一次 dispatch（合并 RED+GREEN） |
| **light-inline** | `tdd_mode=light` 且 LOC≤`TDD_LIGHT_LOC_THRESHOLD` 且 `security_sensitive=false` 且执行模式 ∈ {agile-lite, agile-prototype} | orchestrator 主线程内联 implementer 行为，零子代理 boot |
| **prototype-inline** | 执行模式 = `agile-prototype` | 同 light-inline，强制跳过 REFACTOR |

## Mid-Progress Drop Contract

避免子代理在末尾 finalize 集中产出导致 task-notification truncation（征兆：100+ tools / 100K+ tokens / 5min+ 被打断；`<agent-result>` 不返回但 artifact 已部分落地）。**触发**（任一命中）：`loc_estimate > 200`（缺字段取 `len(AC) × 30`）或 `len(tdd_acceptance) > 6`。命中时 implementer dispatch prompt 强制注入：

> **Mid-progress 落盘**：
> 1. 先 `Write` 全部目标文件的**空骨架**（import + export stub + `describe(...)` / 函数签名占位）
> 2. 逐 AC 迭代填充实现 + 测试
> 3. 每完成一条 AC 立刻运行 `{test_command}`（按需附 file 过滤）验证
> 4. **禁止**末尾一次 `Edit` 堆所有 AC 实现 + 全套断言

适用：standard Step 3 GREEN ✅；light-dispatch ✅；light-inline / prototype-inline ❌（主线程产出，token 由主线程窗口管理，不需此契约）。契约失效（仍 truncation）→ ORCHESTRATOR-PROTOCOLS §Sub-Agent Truncation Recovery Protocol 主线程接管。

## TDD 子代理共享约束

以下约束适用于所有 TDD 子代理，通过 AGENT.md 的 disallowedTools 和本节定义：

- AskUserQuestion 不可用。如需用户输入，返回 blocked 并在 `<questions>` 描述问题，orchestrator 以 continuation 重启
- 返回 `<agent-result>` 格式（详见 dispatch-prompt.md §COMMON-SECTIONS）
- blocked 时可追加 `<questions>` 字段
- implementer 在 GREEN/Light 完成后必须 self-report `refactor_needed: bool` + `refactor_reasons: [category]`（详见 implementer AGENT.md §Output Contract），orchestrator 以此判定是否调度 refactorer

## 输入规范

- dev-plan#T-xxx任务卡(含tdd_acceptance, deliverables, context_load, 可选 task_kind/tdd_mode/tdd_refactor/security_sensitive/loc_estimate)
- 通过doc-nav加载的arch相关章节(接口契约、数据模型、目录结构、命名规范)

## 阶段间传递格式

子代理间通过文件系统传递状态；orchestrator 保留 Step 1 提取的上下文，按阶段按需内联进各 dispatch prompt：

```
RED → GREEN:
  从RED的<agent-result>提取:
  - outputs → test_files路径列表
  - summary → 测试结果(N FAILED, M PASSED)

GREEN → REFACTOR:
  从GREEN的<agent-result>提取:
  - outputs → impl_files路径列表
  - refactor_needed / refactor_reasons → 触发判定
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
  - `light` + 满足 §Inline 触发条件 → 走 §Light Inline 模式（主线程内联，零 dispatch）
  - `light` + 不满足 inline 条件 → 走 §Light Dispatch 模式（implementer 一次 dispatch 合并 RED+GREEN）
  - `standard` → Step 1 → Step 2 (RED) → Step 3 (GREEN) → Step 4 按条件 → Step 5
- 执行模式为 `agile-prototype` → 强制走 §Prototype Inline 模式（主线程内联 + 强制跳过 REFACTOR）

**Inline 触发条件**（合取）:

1. `tdd_mode = light`
2. `loc_estimate ≤ TDD_LIGHT_LOC_THRESHOLD`（任务卡缺该字段时取 LOC=AC 数 × 30 的粗估）
3. `security_sensitive ≠ true`
4. 执行模式 ∈ `{agile-lite, agile-prototype}`（agile-standard 模式即使 light 任务也走 dispatch，保持子代理隔离的审计粒度）

**REFACTOR 条件触发**: 任务卡显式 `tdd_refactor: required` 强制触发；否则 implementer 在 GREEN/Light 完成后通过 `<agent-result>.refactor_needed` 自报告（true 时 orchestrator 调度 refactorer），不再为每个任务跑一次 code-review Layer 1。可在 sprint-review 阶段对累积 impl_files 跑批量 code-review L1 复核（见 ORCHESTRATOR-PROTOCOLS §Sprint Review Protocol）。

### Step 1: 准备任务上下文

通过doc-nav加载任务卡的context_load章节，提取以下内容并在主线程保留，后续子代理 prompt 将按需内联传入：

- 验收标准(tdd_acceptance → AC列表)
- 接口契约(arch#API-xxx)
- 目录结构和命名规范(arch#§6, arch#§7)
- deliverables清单
- 任务卡字段：`task_kind`、`tdd_mode`、`tdd_refactor`、`security_sensitive`、`loc_estimate`
- 测试命令(`test_command`，按技术栈，如 `pytest -q --tb=short tests/`)

### Step 2: RED Phase — 启动test-writer子代理

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD RED: {T-xxx}"`

通过调度接口启动。角色定义、返回格式和异常处理已在 test-writer AGENT.md 中定义，通过 subagent_type 自动加载，prompt 内联任务上下文：

```
调度请求:
  agent_id: "test-writer"
  description: "TDD RED: T-xxx 编写失败测试"
  prompt: |
    当前项目: {项目名}。

    ## meta
    - task_kind: {task_kind}
    - tdd_mode: standard
    - security_sensitive: {true|false}

    ## tdd_acceptance
    {AC列表}

    ## interface_contract
    {arch 接口定义片段}

    ## directory_layout
    {arch#§6 摘要}

    ## test_command
    {如 `pytest -q --tb=short tests/`}

    任务: 为以上 §tdd_acceptance 的所有 AC 编写测试用例，确保所有新增测试 FAIL。
```

> **同模块 RED 批量化** (§C2): 当 orchestrator 一次性派发同 sprint_group 内同模块（context_load 共享 ≥1 个 arch#§2.M-xxx）的 N 个任务时，可合并为**一次 test-writer 调用**，prompt 内联各任务的 §tdd_acceptance（按 task_id 分块）和共享的接口契约，summary 中按 task_id 分块返回。仅适用于任务数 ≤ 4 且共享同一模块；否则回退到逐任务调度。

验证（orchestrator 执行）:

1. 确认新增测试均为 FAILED。标记为"pre-existing"的 PASSED 测试不视为异常。
2. summary 中如有异常，按错误分级处理 continuation：
   - **机械错** (SyntaxError / ImportError / 配置错 / 路径错) → 允许 continuation 至多 3 次，每次都明确告知具体错误信息
   - **语义错** (AC 含糊 / 测试断言不匹配契约 / 测试与 AC 不对应) → 至多 1 次 continuation，再失败则 blocked 请求人工介入

  > 失败原因验证和断言有效性已由 test-writer 的 Execution Rules 完成；orchestrator 不再做 summary 字段级二次核验，避免主线程上下文重复消费 test-writer 详细输出。

### Step 3: GREEN Phase — 启动implementer子代理

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD GREEN: {T-xxx}"`

通过调度接口启动。角色定义、返回格式和异常处理已在 implementer AGENT.md 中定义，通过 subagent_type 自动加载，prompt 内联任务上下文：

```
调度请求:
  agent_id: "implementer"
  description: "TDD GREEN: T-xxx 最小实现"
  prompt: |
    当前项目: {项目名}。

    ## meta
    - task_kind: {task_kind}
    - tdd_mode: standard
    - security_sensitive: {true|false}

    ## interface_contract
    {arch 接口定义片段}

    ## directory_layout
    {arch#§6 摘要}

    ## naming_convention
    {arch#§7 摘要}

    ## test_command
    {如 `pytest -q --tb=short tests/`}

    RED 阶段产出 test_files: {RED 阶段返回的路径列表}

    任务: 编写最小代码使所有测试通过。在 <agent-result> 中报告 refactor_needed (true/false) 与 refactor_reasons（命中 complexity/duplication/coupling 的具体说明）。

    {{ 当 loc_estimate > 200 或 len(tdd_acceptance) > 6 时附加 }}
    见 §Mid-Progress Drop Contract，必须按 4 步契约推进（先骨架 → 逐 AC 填充 → 每 AC 后跑测试 → 禁止末尾堆批 Edit）。
```

验证: 确认返回的 test-result 全部 PASSED；解析 `refactor_needed` / `refactor_reasons` 字段。continuation 同 §Step 2 错误分级。

### Step 4: REFACTOR Phase — 条件触发 (可选)

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD REFACTOR: {T-xxx}"`（仅在实际触发时记录）

**触发判定** (orchestrator 在 GREEN/Light 完成后执行):

1. 任务卡 `tdd_refactor: required` → 强制触发
2. 任务卡 `tdd_refactor: skip` → 直接跳过进入 Step 5
3. 缺省 → 读取 GREEN/Light 阶段 `<agent-result>.refactor_needed`：
   - true → 触发，`refactor_reasons` 作为 prompt §触发原因 内联
   - false / 缺失 → 跳过

> **审计兜底**：sprint-review 阶段对该 sprint 的所有 impl_files 跑一次批量 `code-review --focus complexity,duplication,coupling`（Layer 1），覆盖 implementer 漏判的情况。

触发后通过调度接口启动，prompt 内联必要上下文：

```
调度请求:
  agent_id: "refactorer"
  description: "TDD REFACTOR: T-xxx 代码优化"
  prompt: |
    当前项目: {项目名}。

    ## meta
    - tdd_refactor: {required|self-report}
    - security_sensitive: {true|false}

    ## naming_convention
    {arch#§7 摘要}

    ## test_command
    {如 `pytest -q --tb=short tests/`}

    实现文件: {GREEN阶段产出的impl_files}
    测试文件: {RED阶段产出的test_files}
    触发原因: {required | implementer self-report: <refactor_reasons>}（请重点优化对应维度）

    任务: 优化代码质量，保持所有测试通过。
```

跳过 REFACTOR 时不记录 tdd_phase REFACTOR 事件，仅在 Step 5 汇总中标注 "REFACTOR skipped (no trigger)"。

> **并行约束**：REFACTOR 阶段在同 sprint_group 批次内必须**串行**（按 task_id 字典序），不可与其他任务的 REFACTOR 并行执行。约束来源 ORCHESTRATOR-PROTOCOLS §Parallel Task Dispatch（避免源文件并发改写冲突）。RED / GREEN 仍可并行（上限 3）。

### Light Dispatch 模式: 合并 RED+GREEN (tdd_mode=light, 不满足 inline 条件)

将 Step 2 和 Step 3 合并为一次 implementer 子代理调用，子代理内部先写 AC 对应的失败测试再补最小实现。

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD LIGHT-DISPATCH: {T-xxx}"`

通过调度接口启动，prompt 内联任务上下文：

```
调度请求:
  agent_id: "implementer"
  description: "TDD LIGHT-DISPATCH: T-xxx 合并RED+GREEN"
  prompt: |
    当前项目: {项目名}。
    模式: tdd_mode=light（合并 RED+GREEN）

    ## meta
    - task_kind: {task_kind}
    - security_sensitive: {true|false}

    ## tdd_acceptance
    {AC列表}

    ## interface_contract
    {arch 接口定义片段}

    ## directory_layout
    {arch#§6 摘要}

    ## naming_convention
    {arch#§7 摘要}

    ## test_command
    {如 `pytest -q --tb=short tests/`}

    任务: 先为以上 §tdd_acceptance 的每条 AC 写一份失败测试，确认 FAIL 后再补最小实现使测试通过。

    === 输出要求 ===
    在 <agent-result>.outputs 中同时返回:
      - test_files: [...]
      - impl_files: [...]
    summary 中标注: "light mode — RED+GREEN 合并，最终测试全部 PASSED"
    必须报告 refactor_needed / refactor_reasons。

    {{ 当 loc_estimate > 200 或 len(tdd_acceptance) > 6 时附加 }}
    见 §Mid-Progress Drop Contract，必须按 4 步契约推进（先骨架 → 逐 AC 填充 → 每 AC 后跑测试 → 禁止末尾堆批 Edit）。
```

验证（orchestrator 执行）:

1. 确认 outputs 同时含 test_files 和 impl_files
2. 运行测试确认最终全部 PASSED
3. REFACTOR 处理：按 §Step 4 条件触发判定执行（agile-prototype 强制跳过；其它模式按 implementer self-report）

### Light Inline 模式 (tdd_mode=light + 满足 §Inline 触发条件)

orchestrator 自身在主线程使用 Step 1 已提取的上下文，按 light 模式的"先测试后实现"步骤直接产出 test_files + impl_files，**不调用 agent_dispatch capability**：

- 步骤等同 light-dispatch 的 implementer 内部行为
- self-report `refactor_needed` / `refactor_reasons` 作为 orchestrator 自身的判断（写入 EVENT-LOG 而非通过 agent_return）
- REFACTOR 处理：同 light-dispatch
- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD LIGHT-INLINE: {T-xxx}"`

收益：节省一次子代理 boot（AGENT.md + COMMON-RULES + dispatch-prompt 模板加载约 3-5K token）。

### Prototype Inline 模式 (执行模式 = agile-prototype)

agile-prototype 项目的任务全部走 implementer **主线程内联**（即 light-inline 的特化），并强制跳过 REFACTOR：

- 与 light-inline 步骤相同（先测试后实现，主线程产出）
- **强制跳过** Step 4 REFACTOR（prototype 不进 sprint-review，重构延迟到正式化时再处理）
- 跳过 per-task code-review（lint hook 已兜底）
- **[EVENT]** `cataforge event log --event tdd_phase --phase development --detail "TDD PROTOTYPE-INLINE: {T-xxx}"`

### Step 5: 汇总与状态更新

orchestrator完成以下收尾:

1. 验证最终测试结果(运行测试确认全部PASS)
2. 核对deliverables清单(所有文件已创建)
3. 触发代码审查时，审查范围包含 impl_files 和 test_files（测试代码质量纳入 code-review Layer 2）；按 code-review §Layer 2 短路条件判断是否仅跑 Layer 1
4. 通过doc-gen(write-section)将dev-plan#§1对应任务行状态更新为done
5. 如 blocked 且含 questions → 按 ORCHESTRATOR-PROTOCOLS.md §TDD Blocked Recovery Protocol 处理
6. 如 blocked 且无 questions → 记录原因并请求人工介入

> **Sprint级审查**: 当Sprint内所有任务完成Step 5后，orchestrator触发sprint-review skill执行Sprint完成度审查（见 ORCHESTRATOR-PROTOCOLS.md §Sprint Review Protocol）。Sprint审查在所有任务的code-review之后、下一Sprint开始之前执行；包含批量 `code-review --focus complexity,duplication,coupling` 兜底覆盖 implementer self-report 的漏判。

## 效率策略

- 每个子代理拥有独立上下文，避免阶段间污染
- 子代理间仅传递文件路径，非代码全文
- 按context_load加载最小必要上下文
- **light-inline 默认（agile-lite/prototype）**：典型小任务从 3 次子代理调度收敛到 0 次，主线程直接产出
- **light-dispatch（agile-standard 的 light 任务）**：保持子代理隔离审计，1 次 dispatch 合并 RED+GREEN
- **REFACTOR 由 implementer self-report 触发**：消除每任务一次 code-review L1 的固定开销；sprint-review 阶段批量复核兜底
- **同模块 RED 批量化**：sprint_group 内任务共享模块时，test-writer 一次写完多任务测试，减少子代理 boot 次数
