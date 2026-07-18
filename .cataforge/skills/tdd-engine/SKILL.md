---
name: tdd-engine
description: "TDD引擎 — 编排RED→GREEN→REFACTOR三阶段子代理执行TDD开发，支持 light-dispatch / light-inline / standard / prototype-inline 四档与 sprint 内独立任务并行调度。"
argument-hint: "<任务卡ID如T-001>"
suggested-tools: file_read, file_write, file_edit, shell_exec, file_glob, file_grep, agent_dispatch
depends: [context]
disable-model-invocation: false
user-invocable: true
---

# TDD引擎 (tdd-engine)

## 能力边界

- 能做: 指导orchestrator编排TDD三阶段子代理(RED/GREEN/REFACTOR)、light-dispatch/light-inline/standard 档位路由、prototype 主线程内联实现、同 sprint_group 独立任务并行调度、定义子代理prompt模板
- 不做: 需求分析、架构设计、文档生成、集成测试 / E2E 测试（由 testing skill 负责，本 skill 限单元测试粒度的 RED/GREEN/REFACTOR）

## 架构说明

orchestrator作为主线程Agent，在Phase 5逐任务执行时调用本skill。每个TDD阶段作为独立子代理启动，拥有独立上下文窗口，避免阶段间上下文污染。

```
orchestrator (主线程)
  ├─ 通过调度接口启动 → RED SubAgent (test-writer) — 独立上下文
  ├─ 收集RED产出 → 通过调度接口启动 → GREEN SubAgent (implementer) — 独立上下文
  ├─ implementer self-report `refactor_needed=true` 或 `tdd_refactor: required` → REFACTOR SubAgent (refactorer)
  └─ 汇总产出 → 更新dev-plan任务状态
```

四档执行模式（触发条件唯一定义在 §执行流程 任务路由分支）：

| 档 | 执行位置 |
|---|---------|
| **standard** | RED + GREEN + REFACTOR(条件) 三次 dispatch |
| **light-dispatch** | implementer 一次 dispatch（合并 RED+GREEN） |
| **light-inline** | orchestrator 主线程内联 implementer 行为，零子代理 boot |
| **prototype-inline** | 同 light-inline，强制跳过 REFACTOR |

## Mid-Progress Drop Contract

避免子代理在末尾 finalize 集中产出导致 task-notification truncation（征兆：100+ tools / 100K+ tokens / 5min+ 被打断；`<agent-result>` 不返回但 artifact 已部分落地）。**触发**（任一命中）：`loc_estimate > MID_PROGRESS_LOC`（缺字段取 `len(AC) × 30`）或 `len(tdd_acceptance) > 6`。命中时 implementer dispatch prompt 强制注入：

> **Mid-progress 落盘**：
> 1. 先 `Write` 全部目标文件的**空骨架**（import + export stub + `describe(...)` / 函数签名占位），按**依赖序**落盘——被导入文件先于引用它的文件（写盘纪律见 SUB-AGENT-PROTOCOLS §并行/多文件写盘纪律）
> 2. 逐 AC 迭代填充实现 + 测试
> 3. 每完成一条 AC 立刻运行 `{test_command_fast}`（按需附 file 过滤）验证
> 4. **禁止**末尾一次 `Edit` 堆所有 AC 实现 + 全套断言

适用：standard Step 3 GREEN ✅；light-dispatch ✅；light-inline / prototype-inline ❌（主线程产出，token 由主线程窗口管理，不需此契约）。契约失效（仍 truncation）→ ORCHESTRATOR-RECOVERY-PROTOCOLS §Sub-Agent Truncation Recovery Protocol 主线程接管。

## TDD 子代理共享约束

以下约束适用于所有 TDD 子代理，通过 AGENT.md 的 disallowedTools 和本节定义：

- 各 Step 的 dispatch 块：角色定义 / 返回格式 / 异常处理由对应 AGENT.md 经 subagent_type 自动加载，prompt 仅内联任务上下文，各 Step 不再重述
- AskUserQuestion 不可用。如需用户输入，返回 blocked 并在 `<questions>` 描述问题，orchestrator 以 continuation 重启
- 返回 `<agent-result>` 格式（详见 dispatch-prompt.md §COMMON-SECTIONS）
- blocked 时可追加 `<questions>` 字段

## 输入规范

- dev-plan#T-xxx任务卡(含tdd_acceptance, deliverables, context_load, 可选 task_kind/tdd_mode/tdd_refactor/security_sensitive/loc_estimate)
- 通过context加载的arch相关章节(接口契约、数据模型、目录结构、命名规范)

## 阶段间传递格式

子代理间通过文件系统传递状态；orchestrator 保留 Step 1 提取的上下文，按阶段按需内联进各 dispatch prompt。各阶段从上一阶段 `<agent-result>` 提取（字段定义 SSOT=各 AGENT.md §Output Contract）：

- RED → GREEN: outputs（test_files 路径列表）+ summary（测试结果 N FAILED, M PASSED）
- GREEN → REFACTOR: outputs（impl_files 路径列表）+ refactor_needed / refactor_reasons（触发判定）；合并 RED 阶段的 test_files 一并传入
- REFACTOR → orchestrator: outputs（最终文件路径列表）+ summary（测试结果 + 重构变更摘要）

## 执行流程

orchestrator按以下步骤编排每个任务(T-xxx)的TDD。

**任务路由分支**: 读取任务卡 `task_kind` 和 `tdd_mode` 字段:

- `task_kind` ∈ `CODE_REVIEW_L2_SKIP_TASK_KINDS` → **跳过 TDD**，由 implementer 单次调用直接产出，进入 Step 5。**产代码的 chore 任务**（deliverables 含源码而非纯配置/文档）标 done 前须跑一次 changed-scope 类型检查 + lint 门，命中即 continuation 修复，不寄托于 self-report 或 lint hook 兜底
- `tdd_mode` 缺省（缺省视为 `TDD_DEFAULT_MODE`）:
  - `light` + 满足 §Inline 触发条件 → 走 §Light Inline 模式（主线程内联，零 dispatch）
  - `light` + 不满足 inline 条件 → 走 §Light Dispatch 模式（implementer 一次 dispatch 合并 RED+GREEN）
  - `standard` → Step 1 → Step 2 (RED) → Step 3 (GREEN) → Step 4 按条件 → Step 5
- 执行模式为 `agile-prototype` → 强制走 §Prototype Inline 模式（主线程内联 + 强制跳过 REFACTOR）

**Inline 触发条件**（合取）:

1. `tdd_mode = light`
2. `loc_estimate ≤ TDD_LIGHT_LOC_THRESHOLD`（任务卡缺该字段时取 LOC=AC 数 × 30 的粗估）
3. `security_sensitive ≠ true`
4. 执行模式 ∈ `TDD_INLINE_ELIGIBLE_MODES`（审计粒度通过 EVENT-LOG 事件保持，不依赖子代理隔离）

**REFACTOR 条件触发**: 判定逻辑与审计兜底唯一定义在 §Step 4 触发判定。

### Step 1: 准备任务上下文

通过context加载任务卡的context_load章节，提取以下内容并在主线程保留，后续子代理 prompt 将按需内联传入：

- 验收标准(tdd_acceptance → AC列表)
- 接口契约(arch#API-xxx)
- 目录结构和命名规范(arch#§6, arch#§7)
- deliverables清单
- 任务卡字段：`task_kind`、`tdd_mode`、`tdd_refactor`、`security_sensitive`、`loc_estimate`
- 测试命令两档（arch#§7.4 测试执行口径：`test_command_fast` 内循环排除慢测 / `test_command_full` 收敛点门禁全量；arch 未声明 §7.4 时项目单一测试命令双档同值）
- 用户故事(prd#§2.F-xxx — 任务卡关联的功能需求描述，含用户角色和使用动机)
- 业务规则(prd#§3 — 与本任务相关的业务约束，如有)

### Step 2: RED Phase — 启动test-writer子代理

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --model standard --detail "TDD RED: {T-xxx}"`

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

    ## lang_rules
    按 framework.json project.languages 载入 `testing` skill 的 `references/lang-<active>.md`，遵循其语言测试细则。

    ## suite_discipline
    载入 `.cataforge/references/test-suite-performance.md` 并遵循；新测试涉及子进程/服务/网络/显式等待时，按 arch#§7.4 测试执行口径声明的慢测标签约定打标（未声明时按语言惯例打标并在 summary 注明）。

    ## user_story
    {prd#§2.F-xxx 的功能描述，含用户角色/使用动机/业务价值}

    ## business_rules
    {prd#§3 相关业务规则摘要，无则标注 "无显式业务规则约束"}

    ## tdd_acceptance
    {AC列表，每条 Given-When-Then 格式}

    ## interface_contract
    {arch 接口定义片段}

    ## directory_layout
    {arch#§6 摘要}

    ## test_command
    {test_command_fast，如 `pytest -q --tb=short tests/`（arch#§7.4 未声明时取项目单一测试命令）}

    ## verified_anchors
    {主线程已核实的代码域锚点，按 SUB-AGENT-PROTOCOLS §verified_anchors 锚点传递契约填写；未核实过代码则整节省略}

    任务: 基于 §user_story 的业务场景，为 §tdd_acceptance 的所有 AC 编写验证行为的测试用例（禁止存在性断言），确保所有新增测试 FAIL。
```

> **同模块 RED 批量化**: 当 orchestrator 一次性派发同 sprint_group 内同模块（context_load 共享 ≥1 个 arch#§2.M-xxx）的 N 个任务时，可合并为**一次 test-writer 调用**，prompt 内联各任务的 §tdd_acceptance（按 task_id 分块）和共享的接口契约，summary 中按 task_id 分块返回。仅适用于任务数 ≤ 4 且共享同一模块；否则回退到逐任务调度。

验证（orchestrator 执行）:

1. 确认新增测试均为 FAILED。标记为"pre-existing"的 PASSED 测试不视为异常。
2. summary 中如有异常，按错误分级处理 continuation：
   - **机械错** (SyntaxError / ImportError / 配置错 / 路径错) → 允许 continuation 至多 3 次，每次都明确告知具体错误信息
   - **语义错** (AC 含糊 / 测试断言不匹配契约 / 测试与 AC 不对应) → 至多 1 次 continuation，再失败则 blocked 请求人工介入

  > 失败原因验证和断言有效性已由 test-writer 的 Execution Rules 完成；orchestrator 不做 summary 字段级二次核验，避免主线程上下文重复消费 test-writer 详细输出。

### Step 3: GREEN Phase — 启动implementer子代理

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --model standard --detail "TDD GREEN: {T-xxx}"`

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

    ## lang_rules
    按 framework.json project.languages 载入 `tdd-engine` skill 的 `references/lang-<active>.md`，遵循其语言实现细则。

    ## interface_contract
    {arch 接口定义片段}

    ## directory_layout
    {arch#§6 摘要}

    ## naming_convention
    {arch#§7 摘要}

    ## test_command
    {test_command_fast，如 `pytest -q --tb=short tests/`（arch#§7.4 未声明时取项目单一测试命令）}

    ## verified_anchors
    {主线程已核实的代码域锚点，按 SUB-AGENT-PROTOCOLS §verified_anchors 锚点传递契约填写；未核实过代码则整节省略}

    RED 阶段产出 test_files: {RED 阶段返回的路径列表}

    任务: 编写最小代码使所有测试通过。

    {{ §Mid-Progress Drop Contract 触发条件命中时附加 }}
    按你的 AGENT.md §Mid-Progress 落盘契约推进，禁止末尾堆批 Edit。
```

验证（orchestrator 执行）:

1. 确认返回的 test-result 全部 PASSED
2. 解析 `refactor_needed` / `refactor_reasons` 字段（→ §Step 4）
3. 解析 `wiring_complete` / `wiring_evidence`（缺省视为 `n/a`，向后兼容）：
   - `wiring_complete=false` + 任务卡 `user_facing_critical_path: true` → orchestrator 标 HIGH，要求 implementer continuation 修复 wiring 终点（每任务最多 1 次 continuation，再失败 blocked）
   - `wiring_complete=false` + 普通任务 → orchestrator 不阻塞 GREEN，仅在 sprint-review §wiring-completeness 时记入 MEDIUM
   - `wiring_complete=true` + 缺 `wiring_evidence` → 记 INFO 提示后续补 evidence；不阻塞
4. continuation 同 §Step 2 错误分级。

### Step 4: REFACTOR Phase — 条件触发 (可选)

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --model standard --detail "TDD REFACTOR: {T-xxx}"`（仅在实际触发时记录）

**触发判定** (orchestrator 在 GREEN/Light 完成后执行):

1. 任务卡 `tdd_refactor: required` → 强制触发
2. 任务卡 `tdd_refactor: skip` → 直接跳过进入 Step 5
3. 缺省 → 读取 GREEN/Light 阶段 `<agent-result>.refactor_needed`：
   - true → 触发，`refactor_reasons` 作为 prompt §触发原因 内联
   - false / 缺失 → 跳过

> **审计兜底**：sprint-review 阶段对该 sprint 的 impl_files 范围跑一次 `cataforge skill run code-review -- scan <scope> --focus complexity,duplication,coupling`（Layer 1），覆盖 implementer 漏判的情况。

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
    {test_command_fast，如 `pytest -q --tb=short tests/`（arch#§7.4 未声明时取项目单一测试命令）}

    实现文件: {GREEN阶段产出的impl_files}
    测试文件: {RED阶段产出的test_files}
    触发原因: {required | implementer self-report: <refactor_reasons>}（请重点优化对应维度）

    任务: 优化代码质量，保持所有测试通过。
```

**完成后验证**（orchestrator 在 refactorer 返回 completed 后执行）：

1. 跑 `test_command_full` 确认全部 PASS（收敛点门禁）
2. 跑 `git status --short` 与 HEAD 比对调度前 baseline；任一命中视为 refactorer 越权碰 git（refactorer 仅应产出文件，不应 add / commit / push / branch / reset / checkout / stash —— 见 refactorer AGENT.md §Anti-Patterns），标 BLOCKED 并请求人工介入：
   - staged / unstaged 变化中含非本任务 deliverables 外文件
   - HEAD 位移（分支切换或新增 commit）
   - working tree 出现 stash 或 cherry-pick 中间态
3. 校验通过 → 进入 Step 5

跳过 REFACTOR 时不记录 tdd_phase REFACTOR 事件，仅在 Step 5 汇总中标注 "REFACTOR skipped (no trigger)"。

> **并行约束**：REFACTOR 阶段在同 sprint_group 批次内必须**串行**（按 task_id 字典序），不可与其他任务的 REFACTOR 并行执行。约束来源 ORCHESTRATOR-PROTOCOLS §Parallel Task Dispatch（避免源文件并发改写冲突）。RED / GREEN 仍可并行（上限 3）。

### Light Dispatch 模式: 合并 RED+GREEN (tdd_mode=light, 不满足 inline 条件)

将 Step 2 和 Step 3 合并为一次 implementer 子代理调用，子代理内部先写 AC 对应的失败测试再补最小实现。

- **[EVENT]** `cataforge event log --event tdd_phase --phase development --model standard --detail "TDD LIGHT-DISPATCH: {T-xxx}"`

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

    ## lang_rules
    按 framework.json project.languages 载入 `testing` skill `references/lang-<active>.md`（测试细则）+ `tdd-engine` skill `references/lang-<active>.md`（实现细则）。

    ## suite_discipline
    载入 `.cataforge/references/test-suite-performance.md` 并遵循；新测试涉及子进程/服务/网络/显式等待时，按 arch#§7.4 测试执行口径声明的慢测标签约定打标（未声明时按语言惯例打标并在 summary 注明）。

    ## user_story
    {prd#§2.F-xxx 的功能描述，含用户角色/使用动机/业务价值}

    ## business_rules
    {prd#§3 相关业务规则摘要，无则标注 "无显式业务规则约束"}

    ## tdd_acceptance
    {AC列表，每条 Given-When-Then 格式}

    ## interface_contract
    {arch 接口定义片段}

    ## directory_layout
    {arch#§6 摘要}

    ## naming_convention
    {arch#§7 摘要}

    ## test_command
    {test_command_fast，如 `pytest -q --tb=short tests/`（arch#§7.4 未声明时取项目单一测试命令）}

    ## verified_anchors
    {主线程已核实的代码域锚点，按 SUB-AGENT-PROTOCOLS §verified_anchors 锚点传递契约填写；未核实过代码则整节省略}

    任务: 基于 §user_story 的业务场景，先为 §tdd_acceptance 的每条 AC 写一份验证行为的失败测试（禁止存在性断言），确认 FAIL 后再补最小实现使测试通过。

    {{ §Mid-Progress Drop Contract 触发条件命中时附加 }}
    按你的 AGENT.md §Mid-Progress 落盘契约推进，禁止末尾堆批 Edit。
```

验证（orchestrator 执行）:

1. 确认 outputs 同时含 test_files 和 impl_files
2. 跑 `test_command_full` 确认最终全部 PASSED
3. REFACTOR 处理：按 §Step 4 条件触发判定执行（agile-prototype 强制跳过；其它模式按 implementer self-report）

### Light Inline 模式 (tdd_mode=light + 满足 §Inline 触发条件)

orchestrator 自身在主线程使用 Step 1 已提取的上下文，按 light 模式的"先测试后实现"步骤直接产出 test_files + impl_files，**不调用 agent_dispatch capability**：

- 主线程内联时同样参考 Step 1 已提取的 user_story 上下文编写测试（禁止存在性断言）
- 按 framework.json project.languages 载入 `testing` + `tdd-engine` 两 skill 的 `references/lang-<active>.md`（测试细则 + 实现细则），并载入 `.cataforge/references/test-suite-performance.md`（套件性能纪律）
- 步骤等同 light-dispatch 的 implementer 内部行为
- self-report `refactor_needed` / `refactor_reasons` 作为 orchestrator 自身的判断（写入 EVENT-LOG 而非通过 agent_return）
- REFACTOR 处理：同 light-dispatch
- **[EVENT]** `cataforge event log --event tdd_phase --phase development --model inline --detail "TDD LIGHT-INLINE: {T-xxx}"`

### Prototype Inline 模式 (执行模式 = agile-prototype)

agile-prototype 项目的任务全部走 implementer **主线程内联**（即 light-inline 的特化），并强制跳过 REFACTOR：

- 与 light-inline 步骤相同（先测试后实现，主线程产出）
- **强制跳过** Step 4 REFACTOR（prototype 不进 sprint-review，重构延迟到正式化时再处理）
- 跳过 per-task code-review（lint hook 已兜底）
- **[EVENT]** `cataforge event log --event tdd_phase --phase development --model inline --detail "TDD PROTOTYPE-INLINE: {T-xxx}"`

### Step 5: 汇总与状态更新

orchestrator完成以下收尾:

1. 验证最终测试结果（跑 `test_command_full` 确认全部 PASS——收敛点门禁为真值）
2. 核对deliverables清单(所有文件已创建)
3. 代码审查分级触发:
   - **即时 per-task code-review**（reviewer dispatch）: 仅对满足以下任一条件的任务触发：`security_sensitive: true`、`user_facing_critical_path: true`、`consumer_components` 非空。审查范围包含 impl_files 和 test_files
   - **延迟到 sprint-review 批量审查**: 其余任务不触发 per-task code-review，由 sprint-review 的批量 code-review 覆盖（见 ORCHESTRATOR-PROTOCOLS §Sprint Review Protocol）
   - **prototype-inline**: 跳过 per-task code-review
4. 更新任务状态为 done：graph 模式 `cataforge context update <task-id> --slot task_status=done` 直写任务实体（`task_status` 为 TaskStatusEnum 槽，非法值或非法转换会被拒绝；确需越迁加 `--ack-status-jump`）；markdown 模式直接编辑文档状态行（dev-plan Sprint 表状态列 / brief 任务卡 status 字段，文档即事实源）
5. 如 blocked 且含 questions → 按 ORCHESTRATOR-RECOVERY-PROTOCOLS.md §TDD Blocked Recovery Protocol 处理
6. 如 blocked 且无 questions → 记录原因并请求人工介入

> **Sprint级审查**: 当 Sprint 内所有任务完成 Step 5 后、下一 Sprint 开始之前，orchestrator 触发 sprint-review skill（批量 code-review 与完成度 / AC 覆盖 / 范围偏移的双重职责见 ORCHESTRATOR-PROTOCOLS §Sprint Review Protocol）。

## Anti-Patterns

- 禁止: 在 agile-prototype 模式跑 standard TDD — prototype 设计是快速试错，跑完整三阶段会让重构延迟到正式化时丢失上下文
- 禁止: 绕过 Mid-Progress Drop Contract 让 implementer 末尾批量 Edit — 触发条件命中时必须按 4 步契约执行，否则大概率触发子代理 truncation
- 禁止: 在 light-inline / prototype-inline 档调用 agent_dispatch — 内联档核心收益是省 boot token，调度子代理会让 inline 失效且违反 §Inline 触发条件
- 禁止: REFACTOR 阶段修改测试 assertion 让 GREEN 通过 — refactorer 必须在不动行为契约前提下保持测试 PASS，触发后 ORCHESTRATOR-RECOVERY-PROTOCOLS §Rolled-back Recovery Protocol 接管
- 避免: REFACTOR 跨 sprint_group 并行 — 同 sprint_group 内 REFACTOR 必须串行（按 task_id 字典序），避免源文件并发改写冲突
