# Orchestrator Protocols

> 协议快速定位 — 核心协议: Bootstrap, **Mode Routing**, Interrupt-Resume, Revision, Approved-with-Notes, **Phase Transition**, **Manual Review Checkpoint**, Rolled-back Recovery, TDD Blocked Recovery, **Parallel Task Dispatch**, Sprint Review, Change Request, Agent Crash Recovery, **Sub-Agent Truncation Recovery**, needs_revision 计数 | 基础设施: Event Log | 学习协议: On-Correction Learning, **Adaptive Review (含反向降级)**, Retrospective & Improvement | 模板: CLAUDE.md Update Template

---
# Part 1: 核心协议 (Core Protocols)
> 编排流程的核心生命周期管理。修改需谨慎。
---

## Project Bootstrap
当项目从零开始 (CLAUDE.md 不存在) 时:
1. **收集项目基本信息** — 向用户确认: 项目名称、技术栈、命名规范、Commit格式、分支策略、人工审查检查点偏好（默认 `[pre_dev, pre_deploy]`）
2. **选择执行模式** — 通过 AskUserQuestion 单独提问，选项:
    - `standard`（默认/推荐）— 中大型正式交付项目，7 阶段全流程
    - `agile-lite` — 5-20 feature 的轻量工具或小型 Web 项目（产出 prd-lite / arch-lite / dev-plan-lite 各目标 ≤100 行）
    - `agile-prototype` — 原型 / PoC / 单文件脚本（单一 brief.md 目标 ≤200 行，合并 Phase 1~4）
    完整差异矩阵见 COMMON-RULES §执行模式矩阵。选择结果写入 CLAUDE.md §框架元信息.执行模式
3. **创建目录结构**: 根据执行模式:
    - `standard` / `agile-lite`: `mkdir -p docs/{prd,arch,dev-plan,ui-spec,test-report,deploy-spec,research,changelog,reviews/{doc,code,sprint,retro}}`
    - `agile-prototype`: `mkdir -p docs/{brief,research,reviews/{doc,code}}`
3a. **写入跨平台 `.gitattributes`** — 治理 Windows `core.autocrlf=true` + fixture/snapshot 字节哈希漂移。项目根无 `.gitattributes` 时写入下列最小集；已存在则**只读**判断（含 `eol=` 视为已归一化），不覆盖用户自定义：

    ```
    # cataforge default — 跨平台行尾归一化
    * text=auto eol=lf
    *.md text eol=lf
    *.json text eol=lf
    *.yaml text eol=lf
    *.yml text eol=lf
    *.ts text eol=lf
    *.tsx text eol=lf
    *.js text eol=lf
    *.mjs text eol=lf
    *.py text eol=lf
    *.sh text eol=lf
    *.snap text eol=lf
    *.bat text eol=crlf
    *.cmd text eol=crlf
    *.png binary
    *.jpg binary
    *.jpeg binary
    *.gif binary
    *.ico binary
    *.pdf binary
    *.zip binary
    *.tar.gz binary
    ```

    > 适用：Node / Python / 含 fixture 的多平台项目。纯 Linux/macOS 服务端项目可裁剪至首行 `* text=auto eol=lf`。
4. **创建 CLAUDE.md** — 按下方 Update Template 生成，所有文档状态设为"未开始"，§框架元信息.执行模式填入步骤 2 选定值；当前阶段按模式设置:
    - `standard` → `requirements`
    - `agile-lite` → `planning`（Phase 1+2 合并）
    - `agile-prototype` → `brief`（Phase 1~4 合并）
5. **写入框架版本** — 读取 pyproject.toml 的 `[project].version` 字段填入 CLAUDE.md `框架版本` 字段（如 pyproject.toml 不存在则标注"未追踪"）
6. **选择目标平台** — 通过 AskUserQuestion 单独提问，选项:
    - `claude-code`（默认）— Anthropic Claude Code CLI / Desktop / Web
    - `cursor` — Cursor IDE
    - `codex` — OpenAI Codex CLI
    - `opencode` — OpenCode CLI
    确认后执行: `cataforge setup --platform {选定值}`，该命令将写入 `framework.json` 的 `runtime.platform` 字段并自动执行 deploy，生成对应平台的部署产物。若用户跳过选择则默认 `claude-code`。
7. **填入 §执行环境 + 最小 permissions** — 按顺序运行两条命令:
   - `cataforge setup --emit-env-block`：将输出注入 CLAUDE.md §执行环境 节以替换占位符。退出码 2 表示未检测到已知技术栈，此时将该节内容置为 `- 无自动检测到的标准包管理器（请根据实际技术栈手动填写）`。
   - `cataforge setup --apply-permissions`：根据技术栈最小化平台配置中的 `permissions.allow`（Claude: `.claude/settings.json`，Cursor: `.cursor/hooks.json` + 权限策略），裁掉未使用的 Bash 白名单条目。
   本步骤的目的是让包管理器/安装命令/测试命令以项目指令形式固化到 CLAUDE.md，并收紧运行时权限以符合最小权限原则。
8. **初始化文档索引** — 运行 `cataforge docs index`，生成空的 `docs/.doc-index.json`（首个文档落盘后会被 doc-gen 增量刷新）
9. **进入初始阶段** — 通过 agent-dispatch 激活:
    - `standard` → product-manager（Phase 1 requirements）
    - `agile-lite` → product-manager（planning 阶段，按 §Mode Routing Protocol 产出 prd-lite 后链式激活 architect 产出 arch-lite）
    - `agile-prototype` → product-manager（brief 阶段，产出单一 brief.md）

## Mode Routing Protocol
orchestrator 每次需要决定"下一阶段由哪个 Agent 执行、产出哪份文档"时，先读取 CLAUDE.md §框架元信息.执行模式（字段缺失或占位符未填 → 按 `standard` 处理），然后按下列矩阵路由。模式完整差异见 COMMON-RULES §执行模式矩阵。

### standard 模式
按 7 阶段顺序推进: requirements → architecture → ui_design → dev_planning → development → testing → deployment。阶段可被 CLAUDE.md §框架元信息.阶段配置 标记为 N/A 跳过（ui_design / testing / deployment）。所有 Agent 产出 standard 文档（prd / arch / ui-spec / dev-plan / test-report / deploy-spec）。

### agile-lite 模式
合并 Phase 1+2 为 `planning`，跳过 Phase 3，Phase 4 使用 lite 模板。阶段序列: planning → dev_planning → development → (testing) → (deployment)。

1. **planning 阶段**（合并 Phase 1+2）:
   - 激活 product-manager，传入 `template_id=prd-lite`，产出 `docs/prd/prd-lite-{project}.md`（≤50 行；版本号写入 frontmatter `version:`）
   - prd-lite 通过 doc-review（Layer 1 强制；Layer 2 按 `DOC_REVIEW_L2_SKIP_*` 短路）
   - approved 后**链式**激活 architect（无需额外用户交互窗口），传入 `template_id=arch-lite` + `deps=[prd-lite]`，产出 `docs/arch/arch-lite-{project}.md`
   - arch-lite 通过 doc-review 后 planning 阶段结束
2. **跳过 Phase 3 ui_design** — CLAUDE.md §阶段配置.ui_design 默认标记 N/A；若项目显式需要 UI 设计（Bootstrap 时由用户标注），则 fallback 到 standard ui-designer + ui-spec 流程
3. **dev_planning 阶段**: 激活 tech-lead，传入 `template_id=dev-plan-lite`，任务卡默认 `tdd_mode: light`（tech-lead 按 `TDD_LIGHT_LOC_THRESHOLD` 判定）
4. **development / testing / deployment**: 按 standard 流程推进；Sprint-review 按 `SPRINT_REVIEW_MICRO_TASK_COUNT` 判定；人工检查点仅 `pre_dev`

### agile-prototype 模式
合并 Phase 1~4 为 `brief`，跳过 Phase 3，直接进入 development。阶段序列: brief → development。

1. **brief 阶段**（合并 Phase 1~4）:
   - 激活 product-manager，传入 `template_id=brief`，产出 `docs/brief/brief-{project}.md`（目标 ≤200 行）
   - brief.md §5 即任务卡清单（T-xxx），任务卡默认 `tdd_mode: light`，REFACTOR 跳过
   - brief.md 仅跑 doc-review Layer 1（`DOC_REVIEW_L2_SKIP_DOC_TYPES` 含 brief，Layer 2 直接短路）
2. **跳过 Phase 3 ui_design** — 原型默认无 UI 设计阶段
3. **development 阶段**: orchestrator 直接从 brief.md §5 读取任务卡，按 tdd-engine §Prototype Inline 模式（implementer 主线程内联，不 dispatch 子代理）执行；Sprint-review 跳过；Retrospective 跳过；人工检查点 `none`
4. **testing / deployment**: 默认跳过（CLAUDE.md §阶段配置 标记 N/A）；若用户显式启用，fallback 到 standard 流程

### 路由时机
Mode Routing Protocol 在以下时刻被调用:
- Bootstrap 完成后首次进入初始阶段
- 每次 Phase Transition Protocol Step 6（激活下一阶段 Agent）前，用于确定"下一阶段"的具体含义
- 会话恢复时（Startup Protocol 读取 CLAUDE.md 后）

### 模式回退
- `agile-lite` / `agile-prototype` 运行中若 orchestrator 检测到以下信号，应通过 AskUserQuestion 提示用户切换到更高档位模式: brief.md 实际产出超过 DOC_SPLIT_THRESHOLD_LINES；agile-lite 任务数 >25；或任何 lite 文档超过 150 行且仍无法表达核心决策。切换由用户手动编辑 CLAUDE.md §框架元信息.执行模式完成，orchestrator 不自动改写该字段。

## Interrupt-Resume Protocol
注: 前台子代理(默认)可直接使用AskUserQuestion向用户提问。本协议仅在后台子代理返回 needs_input 时触发。
当Agent返回 needs_input 状态时（orchestrator 侧职责）:
1. 从 `<agent-result>` 中提取 questions、intermediate-outputs、resume-guidance
2. 使用 AskUserQuestion 展示问题（见 COMMON-RULES §MAX_QUESTIONS_PER_BATCH，选择题优先）
3. 收集回答，组织为 `Q1: {问题} → A: {回答}` 格式
4. 通过 agent-dispatch 重新激活同一Agent (task_type=continuation)
5. 循环控制: 每Agent每阶段最多2轮interrupt-resume，第3轮请求人工介入

> 子代理收到 `task_type=continuation` 后的恢复步骤见 `.cataforge/rules/SUB-AGENT-PROTOCOLS.md §task_type=continuation 恢复流程`，orchestrator 无需关注子代理内部执行细节。

## Revision Protocol
当 reviewer 返回 needs_revision 时，先记录审查结论:
- **[EVENT]** `cataforge event log --event review_verdict --phase {当前阶段} --agent reviewer --status needs_revision --detail "审查不通过，需修订"`

当文档状态为 needs_revision 时（orchestrator 侧职责）:
1. **[EVENT]** 记录修订开始:
   ```bash
   cataforge event log --event revision_start --phase {当前阶段} --agent {原Agent} --detail "进入修订流程 needs_revision(N)"
   ```
2. 确认 docs/reviews/doc/ 下存在对应 REVIEW 报告（取编号最大的 `-r{N}` 文件）
3. 通过 agent-dispatch 调度原Agent (task_type=revision)，传递REVIEW报告路径
4. 修复完成后重新激活 reviewer 执行门禁
5. 更新返工计数: needs_revision(N)

> 子代理收到 `task_type=revision` 后的修订步骤见 `.cataforge/rules/SUB-AGENT-PROTOCOLS.md §task_type=revision 修订流程`。

## Approved-with-Notes Protocol
当 reviewer 返回 approved_with_notes 时:
1. **[EVENT]** 记录审查结论:
   ```bash
   cataforge event log --event review_verdict --phase {当前阶段} --agent reviewer --status approved_with_notes --detail "审查通过但有建议"
   ```
2. 从 REVIEW 报告中提取 MEDIUM/LOW 问题列表
3. 使用 AskUserQuestion 向用户展示问题摘要，提供选项:
   - **(1) 接受并继续**: 文档状态 → approved，进入下一 Phase
   - **(2) 要求修复选中的问题**: 选中问题 → needs_revision，进入 Revision Protocol
   - **(3) 暂停等待人工**: 不动文档状态，§当前阶段 标 hold
   - **(4) 全量 inline-fix 后继续**（仅在下列条件**全部**成立时展示）: orchestrator/reviewer 主线程逐条扫 LOW 并 Edit / doc-gen write-section 直接修复（同会话），verdict 保持 approved_with_notes 但实质等价 approved，文档 status: draft → approved
     - MEDIUM+LOW 问题数 ≥ 8（少量手修更直接）
     - 全部为表述漂移 / 格式 / 引用对齐 / 完整性补充（非设计缺陷）
     - 单次修改 ≤ 50 行（超过走 (2)）
     - 不适用 PRD / ARCH 等需求冻结类文档（仍走 (2)，防止冻结后静默改动）
4. **[EVENT]** 记录用户决策:
   ```bash
   cataforge event log --event user_decision --phase {当前阶段} --detail "用户选择: {接受并继续|要求修复|暂停|全量 inline-fix}"
   ```
5. 选"接受"→ MEDIUM/LOW 保留在 REVIEW 供后续参考；选"全量 inline-fix"→ REVIEW 末尾追加 §Inline-Fix 闭环记录 表（每条 LOW 一行：编号 / 原问题 / 修复 commit-or-diff hash / closed-by-orchestrator）

## Phase Transition Protocol
当 reviewer 返回 approved 或 approved_with_notes 且用户选择"接受并继续"时，执行以下状态持久化步骤:

1. **更新文档头状态** — 将文档内部 `status: draft` / `status: review` 更新为 `status: approved`
2. **更新 CLAUDE.md 文档状态** — 对应文档状态字段标记为 approved
3. **更新 CLAUDE.md 阶段信息** — 按 CLAUDE.md Update Template 更新当前阶段、上次完成、下一步行动、已完成阶段
4. **一致性验证** — 确认文档头 status 与 CLAUDE.md 字段一致
5. **[EVENT BATCH]** 通过 `--batch` 单次 stdin 管道一次性记录 4 条事件（phase_end → review_verdict → state_change → phase_start）:
   ```bash
   cataforge event log --batch <<'EOF'
   {"event":"phase_end","phase":"{当前阶段}","status":"approved","detail":"reviewer 通过"}
   {"event":"review_verdict","phase":"{当前阶段}","agent":"reviewer","status":"approved","detail":"审查通过"}
   {"event":"state_change","phase":"{新阶段}","detail":"CLAUDE.md 阶段更新: {旧阶段} → {新阶段}"}
   {"event":"phase_start","phase":"{新阶段}","detail":"进入{新阶段名}阶段"}
   EOF
   ```
6. **进入下一阶段** — 通过 agent-dispatch 激活下一阶段 Agent

> **关键**: 步骤 1-5 必须在步骤 6 之前全部完成，防止会话恢复时因状态未更新而误判阶段未完成。批量写入保证 4 条事件要么全部落盘要么全部失败，避免审计日志出现半截状态。

## Manual Review Checkpoint Protocol
阶段转换时，根据 MANUAL_REVIEW_CHECKPOINTS 常量（见 COMMON-RULES §框架配置常量）决定是否暂停等待用户确认。

**触发时机**: 文档状态变为 approved 且 orchestrator 即将进入下一 Phase 时。

**执行步骤**:
1. 读取 CLAUDE.md §全局约定 中的 `人工审查检查点` 字段（未配置则使用 COMMON-RULES 默认值 `[pre_dev, pre_deploy]`）
2. 判断当前转换是否命中检查点:
   - `phase_transition` → 所有 Phase 转换均命中
   - `pre_dev` → 仅 Phase 4→5（dev_planning → development）命中
   - `pre_deploy` → 仅 Phase 6→7（testing → deployment）命中
   - `post_sprint` → Sprint Review approved 后、进入下一 Sprint 或 Phase 6 前命中
   - `none` → 不命中，直接推进
3. 命中时，使用 AskUserQuestion 向用户展示阶段摘要并确认:
   ```
   === 阶段转换确认 ===
   已完成: {当前阶段名} — {关键产出摘要}
   即将进入: {下一阶段名} — {预期工作概述}

   选项:
   1. 确认继续
   2. 暂停，我需要先审查产出
   3. 调整方向（进入 Change Request 流程）
   ```
4. 用户选择"确认继续" → 正常推进
5. 用户选择"暂停" → orchestrator 等待用户后续指令（不自动推进）
6. 用户选择"调整方向" → 进入 Change Request Protocol

**不命中时**: 直接按现有逻辑自动推进，无额外交互。

## Rolled-back Recovery Protocol
当 TDD REFACTOR 子代理返回 `rolled-back` 状态时:
1. **[EVENT]** 记录异常事件:
   ```bash
   cataforge event log --event incident --phase development --status rolled-back --detail "REFACTOR rolled-back，使用 GREEN 产出"
   ```
2. 使用 GREEN 阶段产出（impl_files）作为最终产出，跳过重构结果
3. 在 code-review 时标记 MEDIUM 级别问题: "REFACTOR rolled-back，代码质量待后续优化"
4. 不自动重试 REFACTOR，不阻塞后续任务
5. 记录到 dev-plan 对应任务的备注中

## TDD Blocked Recovery Protocol
当 TDD 子代理返回 blocked 且含 `<questions>` 字段时:
1. 提取 questions 列表
2. 使用 AskUserQuestion 向用户展示（见 COMMON-RULES §MAX_QUESTIONS_PER_BATCH，选择题优先）
3. 以 continuation 模式重启同一子代理，传入答案
4. 每阶段最多 1 轮 Blocked Recovery，第 2 次 blocked 请求人工介入

## Parallel Task Dispatch Protocol
当 Phase 5 development 阶段一次推进多个任务时，orchestrator 优先按依赖图并行调度，墙钟时间从 N 倍单任务降到约 1 倍最长依赖链。

**适用前提**:
- task-dep-analysis 已生成 `sprint_groups`（同组无依赖；上游 sprint_group 全部完成后才进入下一组）
- 同一 sprint_group 内的任务都已通过 Step 1（任务上下文已提取）

**并行规则**:
1. **同 sprint_group 任务并行 RED/GREEN/LIGHT**：在**单条主线程消息内**通过 agent_dispatch 工具发出多个调度调用，并发上限 = `min(sprint_group 任务数, 3)`。批次完成后才进入下一阶段，避免阶段交叉
2. **批次内禁止并行 REFACTOR**：refactor 改动源码冲突大；REFACTOR 必须串行（按 sprint_group 内的字典序）
3. **同模块批量化（C2）优先于并行调度**：当 sprint_group 内 ≥2 个任务共享同一 arch#§2.M-xxx 时，先尝试合并为一次 test-writer 调用（见 tdd-engine §RED 批量化），剩余任务再走并行调度
4. **回退条件**：若并行调度任一子代理返回 blocked / needs_input → 取消同批次未启动的调度（已启动的等待返回），降级为串行模式重跑该批次

**事件记录**:
- **[EVENT BATCH]** 一次性记录批次启动（每个调度对应一条 agent_dispatch，由 PreToolUse hook 自动写入）
- 批次完成后 orchestrator 写入 `dispatch_batch_end` 标记到 detail（不新增 event 类型，复用 `state_change`）

**安全护栏**:
- 文件系统竞态：同 sprint_group 任务的 deliverables 必须无路径重叠（已由 task-decomp 在 Phase 4 保证），orchestrator 在派发前再做一次 deliverables 路径并集 vs 单任务路径集合大小校验，命中冲突立即降级串行
- maxTurns 截断：每个并行子代理独立计数，互不影响

**示例（伪代码）**:
```
sprint_group_1 = ["T-001", "T-004"]   # 共享 M-002，可批量化
sprint_group_2 = ["T-002", "T-003"]   # 互独立，可并行

# group 1：单次 test-writer 批量 RED（内联各任务 AC + 共享接口契约）+ 各自 GREEN 并行
batch_dispatch([
  Agent(test-writer, prompt=inline_context[T-001, T-004]),
])
# RED 完成后
batch_dispatch([
  Agent(implementer, T-001, prompt=inline_context+test_files),
  Agent(implementer, T-004, prompt=inline_context+test_files),
])

# group 2：直接并行 LIGHT（各自内联上下文）
batch_dispatch([
  Agent(implementer, T-002, prompt=inline_context+light_mode),
  Agent(implementer, T-003, prompt=inline_context+light_mode),
])
```

## Sprint Review Protocol
当Sprint所有任务完成（dev-plan§1 Sprint表中所有任务状态=done 且 code-review通过）时:

**微型 Sprint 短路判定** (Step 0):
若同时满足以下条件则**跳过 sprint-review**，直接视为 approved:
- 本 Sprint 任务数 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT`
- 所有任务 code-review 结论为 approved（无 MEDIUM/HIGH/CRITICAL 问题）

短路时处理:
1. 在 CLAUDE.md 当前 Sprint 字段追加注记 `sprint-review skipped (micro sprint)`
2. **[EVENT]** 记录跳过事件:
   ```bash
   cataforge event log --event review_verdict --phase development --agent orchestrator --status approved --detail "sprint-review skipped (micro sprint)"
   ```
3. 直接进入下一 Sprint 或 Phase 6

**正常流程** (不满足短路条件时):
1. 通过 agent-dispatch 激活 reviewer (task_type=new_creation, skill=sprint-review)
2. 传入: dev-plan路径, Sprint编号, 所有CODE-REVIEW报告路径, arch文档路径
3. reviewer执行sprint-review skill，产出 `SPRINT-REVIEW-s{N}-r{M}.md`
4. 结果处理:
   - **approved** → 更新CLAUDE.md Sprint字段，进入下一Sprint（或全部Sprint完成后进入Phase 6）
   - **approved_with_notes** → 按 Approved-with-Notes Protocol 处理
   - **needs_revision** → 从SPRINT-REVIEW报告中提取标记为CRITICAL/HIGH的任务ID，仅这些任务重新进入TDD（已通过的任务保持done状态不变）
5. Sprint Review的needs_revision不计入Phase级needs_revision计数（独立跟踪）

## Change Request Protocol
当orchestrator检测到用户输入为变更请求（而非流程推进指令）时:
1. 通过 change-guard skill 分析变更（orchestrator直接执行，无需agent-dispatch）；`<change-analysis>` XML 格式定义见 change-guard SKILL.md §Step 5
2. 向用户展示 `<change-analysis>` 结果，提供选项:
   - "确认执行": 按action路由执行
   - "调整范围": 用户修改变更描述后重新分析
   - "取消": 不执行变更
3. 根据 action 路由:
   - **proceed** → 直接在当前阶段执行变更（不触发文档修订）
   - **amend_then_proceed** → 通过agent-dispatch调度affected_docs的原作者Agent(task_type=amendment)修订文档，每个文档修订后经reviewer审核，全部通过后执行变更
   - **cascade_amendment** → 从最上游affected doc开始逐级修订: PRD → ARCH → UI-SPEC(如适用) → DEV-PLAN，每级修订+审核后才进入下级

### cascade_amendment 中断规则
cascade_amendment 中任一文档修订失败(needs_revision ≥ 3):
1. 暂停后续文档修订，不继续下游文档
2. 已修订的上游文档保持 draft 状态（不标记 approved）
3. 向用户报告失败点和已完成的修订范围，提供选项:
   - "继续修复失败文档": 进入 Revision Protocol 修复当前文档
   - "回滚所有修订": `git checkout -- docs/{affected_dirs}` 恢复所有本轮修订的文档
4. 回滚后变更请求状态重置，用户可调整范围后重新提交

4. 变更完成后回到原阶段继续执行
5. Amendment 与 Revision 的区别: Revision由reviewer发起（修复问题），Amendment由用户发起（适应变更），但执行机制复用agent-dispatch和reviewer审核流程

> 子代理收到 `task_type=amendment` 后的修订步骤见 `.cataforge/rules/SUB-AGENT-PROTOCOLS.md §task_type=amendment 变更修订流程`。

## Framework Upgrade Protocol
框架升级时保持项目状态不变:

### 可安全覆盖（框架文件）
- .cataforge/agents/ — 所有 AGENT.md
- .cataforge/skills/ — 所有 SKILL.md + templates/ + scripts/
- .cataforge/rules/ — COMMON-RULES.md, SUB-AGENT-PROTOCOLS.md
- .cataforge/agents/orchestrator/ — ORCHESTRATOR-PROTOCOLS.md
- .cataforge/hooks/ — 所有 Hook 脚本 (.py)
- .cataforge/scripts/framework/ — `setup.py`（环境探测/平台配置）、`event_logger.py`（`cataforge event log` 的路径稳定 shim，供 markdown 协议调用）；其他框架能力（upgrade、docs load/index 等）已上收为 `cataforge` CLI 子命令；Penpot 集成无需 scaffold 落盘脚本，全部通过 `cataforge penpot {deploy|mcp-only|start|stop|status|ensure}` 子命令暴露（实现位于 `cataforge.integrations.penpot`）
- .cataforge/framework.json
- pyproject.toml

### 绝不触碰（项目数据）
- CLAUDE.md 的 "项目状态" 段
- docs/ 目录下所有文档
- src/ 目录下所有代码
- .cataforge/learnings/ 下的经验文件

### 需要合并（混合文件）
- 平台配置文件（Claude: `.claude/settings.json` / `.mcp.json`；Cursor: `.cursor/hooks.json` / `.cursor/mcp.json`）— 保留项目 env、自定义 permissions、MCP 配置
- .cataforge/framework.json — upgrade.source 保留用户已配置的 repo/url，仅补充新字段；upgrade.state 为项目本地升级状态，始终保留；features 和 migration_checks 为框架出厂配置，全量覆盖
- CLAUDE.md 全局约定 — 保留用户已填写的值，新增框架默认字段

### 初始化安装
- 运行: `cataforge setup` 检测环境并安装依赖
- 可选 Penpot: `cataforge setup --with-penpot`
- 仅检测: `cataforge setup --check-prereqs`

### 升级步骤（本地路径方式）
适用场景：想用一个本地 CataForge 仓库的 checkout 升级，而不是从 PyPI/远程安装。
1. 安装目标版本到当前环境: `pip install <新版CataForge路径>`（或 `uv tool install <路径>`）
2. 运行: `cataforge upgrade apply --dry-run` 预览变更
3. 确认变更列表无异常
4. 运行: `cataforge upgrade apply` 执行升级（scaffold 刷新；用户状态保留）
5. 运行: `cataforge upgrade verify` 执行升级后验证（= `cataforge doctor`）
6. 检查: `git diff .cataforge/` 确认变更合理
7. 提交: `git commit -m "chore: upgrade CataForge framework to vX.Y.Z"`

### 升级步骤（PyPI/远程方式）
1. 升级包: `pip install --upgrade cataforge`（或 `uv tool upgrade cataforge`）
2. 运行: `cataforge upgrade check` 对比已安装包版本与 scaffold 版本
3. 运行: `cataforge upgrade apply --dry-run` 预览变更
4. 运行: `cataforge upgrade apply` 执行 scaffold 刷新
5. 检查: `git diff .cataforge/` 确认变更合理
6. 提交: `git commit -m "chore: upgrade CataForge framework to vX.Y.Z"`

### 独立验证
- 运行: `cataforge upgrade verify` 可随时检查框架文件完整性

## Agent Crash Recovery Protocol
当子代理返回结果不含 `<agent-result>` 标签且 agent-dispatch 的标签缺失兜底也无法推断状态时（即真正的崩溃/截断场景）:
1. 通过 `git status docs/ src/` 检查是否有本次调度后的新增或修改文件
2. 向用户展示崩溃信息和部分产出情况，提供选项:
   - "从部分产出继续": 以 continuation 模式重新调度同一Agent，传入已有产出路径
   - "从头重试": 以 new_creation 模式重新调度同一Agent（先 `git checkout -- docs/{相关目录}` 清理部分产出）
   - "跳过此阶段": 仅在非关键路径阶段可用，标记阶段为 blocked 并请求人工后续处理
3. 每Agent每阶段最多 1 次 Crash Recovery，第 2 次崩溃请求人工介入
4. 崩溃事件记录到 docs/reviews/CORRECTIONS-LOG.md 供 reflector 分析

> **与 §Sub-Agent Truncation Recovery 的区分**：本协议针对 process 死（无任何输出 / agent-dispatch 端兜底无法推断状态）。task-notification truncation 是另一回事 —— 子代理走完全程但 token budget 耗尽，artifact 已部分落地，仅 `<agent-result>` JSON 没回。后者由下一节专门处理。

## Sub-Agent Truncation Recovery Protocol

当子代理被 task-notification truncation 打断（征兆：100+ tools / 100K+ tokens / 5min+ / `<agent-result>` 缺失，但 `git status` 显示已有未提交 artifact），主线程**接管收尾**而非 blocked：

1. **评估完成度**（按任务类型选 1-2 项）：代码任务跑 `{test_command}` 看 PASS 率 + `biome lint` / `ruff check` / `tsc --noEmit` 看类型/lint 错数；文档任务核对 deliverables 齐全 + frontmatter 完整
2. **决策**：
   - **≥ 70% AC PASS（或 deliverables 齐全）** → 主线程接管：inline-fix 残留 lint/typecheck 错 + 补落盘缺漏 + 补 `<agent-result>` 等价信息到 EVENT-LOG（`event=state_change`，`detail="truncation recovery: main-thread takeover"`）
   - **< 70%** → blocked，请求人工介入（不允许从零接管，成本不可控）
   - **无任何 artifact** → 走 §Agent Crash Recovery（process 死，本协议不适用）
3. **每任务最多 1 次**；第 2 次截断说明 prompt 设计有问题，blocked + 标 backlog 给下次 retrospective
4. 事件记录：`event=state_change` + `agent={truncated_agent_id}` + `detail="truncation recovery: <70%|≥70%>"`，供 reflector 检测频次（≥5 次/月触发 SKILL-IMPROVE）

**与 tdd-engine §Mid-Progress Drop Contract 的关系**：mid-progress 是**预防**（边推进边落盘，降低末尾批量 finalize 的截断概率）；本协议是**事后兜底**。两者协同：契约把 truncation 后的完成度从 0% 抬到 70%+，让本协议阈值可达。

## needs_revision 计数规范
`needs_revision(N)` 中的 N 为本阶段累计返工次数，格式为 `needs_revision(2)` 而非独立字段。
- N=1: 正常修订流程
- N>=2: 触发 Adaptive Review Protocol
- N>=3: 暂停自动推进，请求人工介入

## Event Log 规范
orchestrator 在关键节点向 `docs/EVENT-LOG.jsonl` 追加事件记录，用于审计追踪和 reflector 回顾分析。

**格式**: JSONL（每行一个 JSON 对象），Schema 见 `.cataforge/schemas/event-log.schema.json`
- 必填字段: `ts` (ISO 8601), `event`, `phase`, `detail`
- 可选字段: `agent`, `task_type`, `status`, `ref`

**事件类型与写入时机**:
| 事件 | 触发条件 | 写入方式 |
|------|---------|---------|
| session_start | 会话启动 | **Hook 自动** (session_context.py，含 60 秒 compact 去重；仅此一个事件由 hook 写入，orchestrator 不再手动补写以节省 token) |
| agent_dispatch | 调度子代理前 | **Hook 自动** (log_agent_dispatch.py, PreToolUse Agent) |
| agent_return | 子代理返回结果后 | **Hook 自动** (validate_agent_result.py, PostToolUse Agent) |
| phase_start | Phase Transition Protocol 步骤 5 | **[EVENT]** orchestrator 手动 |
| phase_end | reviewer 返回 approved | **[EVENT]** orchestrator 手动 |
| review_verdict | reviewer 返回审查结论 | **[EVENT]** orchestrator 手动 |
| user_decision | 用户在 Approved-with-Notes / Change Request 中做出选择 | **[EVENT]** orchestrator 手动 |
| revision_start | 进入 Revision Protocol | **[EVENT]** orchestrator 手动 |
| tdd_phase | TDD RED/GREEN/REFACTOR 阶段切换 | **[EVENT]** tdd-engine skill 步骤内嵌 |
| state_change | CLAUDE.md 状态字段变更 | **[EVENT]** orchestrator 手动 |
| doc_finalize | doc-gen finalize 完成 | **[EVENT]** doc-gen skill 步骤内嵌 |
| incident | 崩溃、rolled-back 等异常事件 | **[EVENT]** orchestrator 手动 |
| correction | On-Correction Learning 触发时 | **[EVENT]** orchestrator 手动 |

**写入方式**:
- **Hook 自动**: 由 `.cataforge/hooks/` 中的 hook 脚本自动触发，无需 orchestrator 记忆
- **[EVENT] 手动**: 使用 `cataforge event log` CLI，已嵌入各协议步骤中（标记为 **[EVENT]**）

**禁止旁路** ⚠️：
- 严禁直接 `echo '{...}' >> docs/EVENT-LOG.jsonl` 或 `cat <<EOF >> ...` 等 shell 重定向写入。`cataforge event log` 是唯一会跑 schema 校验的入口；旁路写入会导致 `unknown field`（如 `timestamp` ≠ `ts`）或 `non-enum event`（如 `doc_revision_completed` ≠ `revision_completed`）滑过门禁，被 reflector 消费时才暴露。
- 若发现某个事件类型在枚举中缺失，应该向 `.cataforge/schemas/event-log.schema.json` + `cataforge.core.event_log.VALID_EVENTS` 同时添加（见 §schema 同步），而不是临时绕开 CLI。
- `cataforge doctor` 的 "EVENT-LOG schema sample" 与 "EVENT-LOG bypass guard" 段会捕获这两类违规并在 CI 中失败。

```bash
cataforge event log --event phase_start --phase architecture --detail "进入架构设计阶段"
```

---
# Part 2: 学习协议 (Learning Protocols)
> 自学习反思机制。聚焦三个高价值触发场景。
---

## On-Correction Learning Protocol

**触发条件** (任一命中即记录):
| 信号 | 数据来源 | 执行者 | 严重度 |
|---|---|---|---|
| option-override | AskUserQuestion 用户选项 ≠ `(Recommended)` | hook `detect_correction.py` | hard |
| interrupt-override | Interrupt-Resume 中用户回答推翻 agent `[ASSUMPTION]` | orchestrator (via `cataforge correction record`) | hard |
| review-flag | reviewer 将 `[ASSUMPTION]` 条目判为 CRITICAL/HIGH | hook `detect_review_flag.py` | review |

**写入规则**:
- hook / reviewer 命中时自动 append 到 `docs/EVENT-LOG.jsonl` (event=correction) + `docs/reviews/CORRECTIONS-LOG.md`（格式: date | agent | phase + 触发信号 + 问题/假设 + 基线 + 实际 + 偏差类型）
- 所有路径（hook / CLI）共享 `cataforge.core.corrections.record_correction` 作为唯一写入口，双日志保持同步；orchestrator 勿绕过 CLI 直接手写 EVENT-LOG（会导致 CORRECTIONS-LOG 漏写）
- interrupt-override 时 orchestrator 必须调用：
  ```bash
  cataforge correction record \
    --trigger interrupt-override \
    --agent {被推翻的 agent} --phase {phase} \
    --question "{被推翻的 [ASSUMPTION] 原文}" \
    --baseline "{agent 假设}" --actual "{用户纠正}" \
    --deviation self-caused
  ```
- CORRECTIONS-LOG.md 为追加写入，不覆盖
- 运维诊断：`cataforge doctor` 的 "Hook script importability" 段会在每次启动时校验 hook 模块可导入；失败即表示 option-override / review-flag 通路失效（静默），需 `pip install -e .` 或重装 wheel 修复

**消费**: reflector 在 Retrospective & Improvement 中将该文件作为输入源；仅 `hard` 和 `review` 条目计入 `RETRO_TRIGGER_SELF_CAUSED` 阈值，`soft` 仅用于 Adaptive Review 聚合统计。

## Adaptive Review Protocol
执行者: orchestrator 自身（不启动子代理）

### 收紧分支（默认）
触发条件: 任一文档达到 needs_revision(N>=2)
步骤:
1. 扫描 docs/reviews/doc/ 和 docs/reviews/code/ 下当前阶段的 REVIEW 文件（含 -r{N} 归档版本），提取 root_cause=self-caused 的问题按 category 聚合
2. 同一 category >=2 次 → 在下次 agent-dispatch 调度同一 Agent 时注入临时提示：
   ```
   === 本项目已识别的反复问题 ===
   - {category}: {问题描述}，已出现{N}次
   ```

### 反向降级分支
触发条件: 连续 `ADAPTIVE_REVIEW_DOWNGRADE_CLEAN_TASKS` 个 TDD 任务（默认 10）满足以下全部条件，视为项目质量已稳态：
- code-review verdict 为 approved（无 MEDIUM/HIGH/CRITICAL）
- 对应任务 CORRECTIONS-LOG.md 无新增 hard / review 条目
- 该 Agent 在该阶段近期无 needs_revision

降级动作（持续到下一次任一上述条件失败时取消）:
1. 在 CLAUDE.md `Learnings Registry` 字段写入 `adaptive-review downgraded for {phase}: layer1-only`
2. 后续该阶段 code-review 调用追加 `--layer1-only` 标记，跳过 Layer 2 AI 语义审查（仅 lint + 腐化探针），sprint-review 仍按原规则执行作为兜底
3. **[EVENT]** 记录降级事件:
   ```bash
   cataforge event log --event review_verdict --phase {当前阶段} --agent orchestrator --status approved --detail "adaptive-review downgraded — {N} consecutive clean tasks"
   ```
4. 任一后续任务 code-review 出现 MEDIUM+ 问题或 CORRECTIONS-LOG 写入新 hard 条目 → 立即取消降级，恢复完整 Layer 2 审查并清空"连续 clean"计数

降级是项目级状态，不是 Agent 级别；切阶段（Phase 5 → 6）自动重置。

## Retrospective & Improvement Protocol
触发条件: 所有 Phase 完成后执行一次（不阻塞项目交付）

**执行模式: inline** —— 与 change-guard / Adaptive Review 一致，orchestrator 直接执行 reflector AGENT.md §Retrospective Protocol；reflector 的 `inline_dispatch: true` frontmatter 即此 hint。

步骤:
1. **触发门槛判定**: 满足以下任一条件才触发 retrospective，否则跳过:
   - `docs/reviews/CORRECTIONS-LOG.md` 中 `偏差类型` 累计命中 self-caused 的条目数 ≥ `RETRO_TRIGGER_SELF_CAUSED`，或
   - 本项目任一 REVIEW / CODE-REVIEW / CODE-SCAN / FRAMEWORK-REVIEW 报告包含 CRITICAL 级别问题
   跳过时在 CLAUDE.md `Learnings Registry` 字段记录 `retro skipped (below threshold)` 并**[EVENT]** 写入 `review_verdict`（agent=reflector, status=approved, detail="retro skipped (below threshold)"）
2. **执行 reflector §Retrospective Protocol**: orchestrator 自行加载 `.cataforge/agents/reflector/AGENT.md` §Retrospective Protocol（含 EVENT-LOG.jsonl 扫描），按其步骤 1-7 完成产出
3. 产出文件:
   - docs/reviews/retro/RETRO-{project}-{cycle}.md（`{cycle}` = sprint 编号或迭代标签，仅 slug；版本号写入 frontmatter `version:`，含 EXP 经验条目）
   - docs/reviews/retro/SKILL-IMPROVE-{skill_id}.md（含每条 EXP 对应的具体 Agent/Skill 文件修改建议）
4. orchestrator 向用户展示 RETRO 报告中的经验条目和改进建议
5. 用户审批后执行修改，git commit，message 格式: `learn: apply EXP-{NNN} to {target_file}`
6. reflector 协议遇到不可恢复错误（docs/reviews/ 子目录不存在或全空、EVENT-LOG.jsonl 解析失败）时仅记录 `incident` 事件，不影响项目完成状态
7. **fallback to subagent**: 主对话上下文饱和或用户显式偏好独立 retro 报告时，降级使用 `cataforge agent run reflector --task-type retrospective`；这是逃生通道，不是默认路径

## CLAUDE.md Update Template
每次阶段转换时更新:
```
## 项目状态 (orchestrator专属写入区，其他Agent禁止修改)
- 当前阶段: {phase_name}
- 上次完成: {agent目录名} — {完成的工作描述}
- 下一步行动: {具体的下一步}
- 已完成阶段: [{阶段列表}]
- 当前Sprint: {Sprint编号，非DEV阶段填 —}
- 文档状态:
  - prd: {状态}
  - arch: {状态}
  - ui-spec: {状态}
  - dev-plan: {状态}
  - test-report: {状态}
  - deploy-spec: {状态}
  <!-- changelog 由 devops 产出但不纳入门禁追踪 -->
```
<!-- 状态值: 未开始 | draft | review | approved | needs_revision | needs_revision(N) | N/A -->

---
# Appendix: 框架开发约定
---

## Skill depends 字段语义
SKILL.md frontmatter 中的 `depends` 字段含义:
- 列出本 Skill 执行过程中**会调用**的其他 Skill（调用链依赖）
- 也包含前置条件型依赖（需先完成的 Skill，如 penpot-implement depends penpot-sync）
- 不包含运行环境依赖（如 Python、Node.js）
- 不用于运行时自动校验，仅供开发者参考和 Agent-Skill 匹配审查
- `suggested-tools` 必须包含本 Skill 所有执行路径中**直接使用**的工具（通过 depends 间接使用的工具不重复列出）
