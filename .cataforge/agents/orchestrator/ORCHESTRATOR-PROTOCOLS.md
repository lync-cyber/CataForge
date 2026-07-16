# Orchestrator Protocols

> 阶段调度热路径协议——协议清单以下方各 H2 节为准。冷路径协议按需加载：
>
> - 元运维与学习协议（低频触发、reference 性质）见
>   [`ORCHESTRATOR-META-PROTOCOLS.md`](ORCHESTRATOR-META-PROTOCOLS.md)：Framework Upgrade,
>   Event Log 规范, On-Correction Learning, Adaptive Review (含反向降级), Retrospective & Improvement.
> - 项目初始化（{INSTRUCTION_FILE} 缺失时执行一次）见
>   [`ORCHESTRATOR-BOOTSTRAP-PROTOCOLS.md`](ORCHESTRATOR-BOOTSTRAP-PROTOCOLS.md) §Project Bootstrap.
> - 异常恢复协议族（触发征兆见下方 §Recovery Protocols 触发索引）见
>   [`ORCHESTRATOR-RECOVERY-PROTOCOLS.md`](ORCHESTRATOR-RECOVERY-PROTOCOLS.md).

## Mode Routing Protocol
orchestrator 每次需要决定"下一阶段由哪个 Agent 执行、产出哪份文档"时，先读取 {INSTRUCTION_FILE} §项目信息.执行模式（字段缺失或占位符未填 →
按 `standard` 处理），然后按下列矩阵路由。模式完整差异见 COMMON-RULES §执行模式矩阵。

### standard 模式
按 7 阶段顺序推进: requirements → architecture → ui_design → dev_planning → development → testing →
deployment。阶段可被 {INSTRUCTION_FILE} §项目信息.阶段配置 标记为 N/A 跳过（ui_design / testing / deployment）；每次
N/A 跳过 **[EVENT]** `cataforge event log --event phase_skip --phase {阶段} --detail "N/A per 阶段配置"`（使
EVENT-LOG 可区分「跳过」与「漏跑」）。所有 Agent 产出 standard 文档（prd / arch / ui-spec / dev-plan / test-report
/ deploy-spec）。

### agile-lite 模式
合并 Phase 1+2 为 `planning`，跳过 Phase 3，Phase 4 使用 lite 模板。阶段序列: planning → dev_planning →
development → (testing) → (deployment)。

1. **planning 阶段**（合并 Phase 1+2）:
   - 激活 product-manager，传入 `template_id=prd-lite`，产出 `docs/prd/prd-lite-{project}.md`
   - prd-lite 通过 doc-review
   - approved 后**链式**激活 architect（无需额外用户交互窗口），传入 `template_id=arch-lite` + `deps=[prd-lite]`，
     产出 `docs/arch/arch-lite-{project}.md`
   - arch-lite 通过 doc-review 后 planning 阶段结束
2. **跳过 Phase 3 ui_design** — {INSTRUCTION_FILE} §阶段配置.ui_design 默认标记 N/A；若项目显式需要 UI
   设计（Bootstrap 时由用户标注），则 fallback 到 standard ui-designer + ui-spec 流程
3. **dev_planning 阶段**: 激活 tech-lead，传入 `template_id=dev-plan-lite`，任务卡默认
   `tdd_mode: light`（tech-lead 按 `TDD_LIGHT_LOC_THRESHOLD` 判定）
4. **development / testing / deployment**: 按 standard 流程推进（模式差异见 COMMON-RULES §执行模式矩阵）

### agile-prototype 模式
合并 Phase 1~4 为 `brief`，跳过 Phase 3，直接进入 development。阶段序列: brief → development。

1. **brief 阶段**（合并 Phase 1~4）:
   - 激活 product-manager，传入 `template_id=brief`，产出 `docs/brief/brief-{project}.md`（目标 ≤200 行）
   - brief.md §5 即任务卡清单（T-xxx），任务卡默认 `tdd_mode: light`，REFACTOR 跳过
   - brief.md 通过 doc-review
2. **跳过 Phase 3 ui_design** — 原型默认无 UI 设计阶段
3. **development 阶段**: orchestrator 直接从 brief.md §5 读取任务卡，按 tdd-engine §Prototype Inline
   模式（implementer 主线程内联，不 dispatch 子代理）执行
4. **testing / deployment**: 默认跳过（{INSTRUCTION_FILE} §阶段配置 标记 N/A）；若用户显式启用，fallback 到 standard 流程

### 路由时机
Mode Routing Protocol 在以下时刻被调用:
- Bootstrap 完成后首次进入初始阶段
- 每次 Phase Transition Protocol Step 10（激活下一阶段 Agent）前，用于确定"下一阶段"的具体含义
- 会话恢复时（Startup Protocol 读取 {INSTRUCTION_FILE} 后）

### 模式回退
- `agile-lite` / `agile-prototype` 运行中若 orchestrator 检测到以下信号，应通过 AskUserQuestion
  提示用户切换到更高档位模式: brief.md 实际产出超过 DOC_SPLIT_THRESHOLD_LINES；agile-lite 任务数 >25；或任何 lite 文档超过
  150 行且仍无法表达核心决策。切换由用户手动编辑 {INSTRUCTION_FILE} §项目信息.执行模式完成，orchestrator 不自动改写该字段。

## Interrupt-Resume Protocol
注: 主线程内联承载的 phase 角色（`execution_host: inline`，见 §Inline Role Execution Protocol）直接用
AskUserQuestion 多轮澄清，不经本协议。派发的子代理（`execution_host: subagent`）为非交互执行体，无法直接向用户提问，其澄清须以
needs_input 回传由本协议代问。
当Agent返回 needs_input 状态时（orchestrator 侧职责）:
1. 从 `<agent-result>` 中提取 questions、intermediate-outputs、resume-guidance
2. 使用 AskUserQuestion 展示问题（见 COMMON-RULES §MAX_QUESTIONS_PER_BATCH，选择题优先）
3. 收集回答，组织为 `Q1: {问题} → A: {回答}` 格式
4. 通过 agent-dispatch 重新激活同一Agent (task_type=continuation)
5. 循环控制: 每Agent每阶段最多2轮interrupt-resume，第3轮请求人工介入

> 子代理收到 `task_type=continuation` 后的恢复步骤见 `{RULES_DIR}/SUB-AGENT-PROTOCOLS.md §task_type=continuation 恢复流程`，
> orchestrator 无需关注子代理内部执行细节。

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
4. 修复完成后先按 §Phase Transition Protocol Step 6 执行 reconcile 收口（漂移按 Step 6 选项处置），再重新激活 reviewer
   执行门禁。reviewer 采用**增量审查模式**——与上轮 baseline 比较只审变更，上轮 CRITICAL/HIGH 涉及维度与
   新增内容按全维度审查；完整增量语义以 code-review SKILL §增量审查模式（代码）与
   context review.md §报告（文档）为准
5. 更新返工计数: needs_revision(N)。N≥2 时请求人工介入，避免低效 revision 循环

> 子代理收到 `task_type=revision` 后的修订步骤见 `{RULES_DIR}/SUB-AGENT-PROTOCOLS.md §task_type=revision 修订流程`。

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
   - **(4) 全量 inline-fix 后继续**（仅在下列条件**全部**成立时展示）: orchestrator/reviewer 主线程逐条扫 LOW 并经
     context `write-narrative` 重写所在节（slot 级用 `update`）落图、`context finalize` 重导出（同会话），verdict
     保持 approved_with_notes 但实质等价 approved，文档 status: draft → approved
     - MEDIUM+LOW 问题数 ≥ 8（少量手修更直接）
     - 全部为表述漂移 / 格式 / 引用对齐 / 完整性补充（非设计缺陷）
     - 单次修改 ≤ 50 行（超过走 (2)）
     - 不适用 PRD / ARCH 等需求冻结类文档（仍走 (2)，防止冻结后静默改动）
4. **[EVENT]** 记录用户决策:
   ```bash
   cataforge event log --event user_decision --phase {当前阶段} --detail "用户选择: {接受并继续|要求修复|暂停|全量 inline-fix}"
   ```
5. 选"接受"→ MEDIUM/LOW 保留在 REVIEW 供后续参考；选"全量 inline-fix"→ REVIEW 末尾追加 §Inline-Fix 闭环记录 表（每条 LOW
   一行：编号 / 原问题 / 修复 commit-or-diff hash / closed-by-orchestrator）

## Phase Transition Protocol
当 reviewer 返回 approved 或 approved_with_notes 且用户选择"接受并继续"时，执行以下状态持久化步骤:

1. **更新文档头状态** — 将文档内部 `status: draft` / `status: review` 更新为 `status: approved`
2. **更新 {INSTRUCTION_FILE} 文档状态** — 对应文档状态字段标记为 approved
3. **更新 {INSTRUCTION_FILE} 阶段信息** — 按 {INSTRUCTION_FILE} Update Template 与
   §{INSTRUCTION_FILE} 项目状态写入纪律 更新；状态只留实时摘要，历史写入持久记录
4. **一致性验证** — 确认文档头 status 与 {INSTRUCTION_FILE} 字段一致
5. **依赖新鲜度检查** — 运行 `cataforge context validate`，检查 `stale_deps` 输出：
   - 无 stale deps → 通过，继续 Step 7
   - 存在 stale deps → 向用户展示过期依赖清单并提供选项：
     1. 进入 cascade_amendment 更新受影响文档
     2. 确认变更不影响下游、继续推进（stale deps 降级为 WARN 记录到 EVENT-LOG）
     3. 暂停，手动审查
   - 用户选"确认不影响"时记录 **[EVENT]**: `cataforge event log --event state_change --phase {当前阶段} --detail "stale deps acknowledged: {upstream_ids}"`
6. **一致性最终守门** — 运行 `cataforge context reconcile`（上下文方案未启用图后端时为 no-op，WARN 跳过）:
   - 无漂移 → 通过，继续 Step 7
   - 有漂移 → 向用户展示漂移报告摘要并提供选项：
     1. 自动修复（按 reconcile 报告 `documents[].remediation`）：`export`（图谱领先）→
        `cataforge context finalize` 重导出；`ingest`（md 领先或 md 权威）→ 先归因：本收口点紧跟 Agent
        产出段且期间无人工编辑时，md 领先即 Agent 绕过 authoring 直写了导出文件——向用户报告违纪，回滚 md 侧改动并重走 authoring 落图；
        确认为人改导出文件时才 `cataforge context ingest` 回灌；`manual`（conflict，两侧均变更）→ 转选项 3。修复后复跑
        `cataforge context reconcile`，漂移归零后继续 Step 7
     2. 进入 cascade_amendment 修订上游文档以匹配图谱
     3. 暂停，手动审查
   - 其它错误（store 未初始化等）→ WARN 跳过（记录到 EVENT-LOG 供 reflector 复盘），不阻塞
7. **跨文档一致性校验** — 当至少 2 个业务文档已 approved 时（即 Phase 2+ 的转换），运行
   `cataforge skill run doc-consistency -- docs/`:
   - exit 0（consistent；输出含 MEDIUM/LOW findings 时记录 WARN 到 EVENT-LOG）→ 通过，继续 Step 8
   - exit 1（inconsistent，存在 CRITICAL/HIGH）→ 向用户展示一致性报告摘要并提供选项：
     1. 进入 cascade_amendment 修复不一致
     2. 降级为 WARN 继续推进（记录到 EVENT-LOG）
     3. 暂停，手动审查
   - exit 2 / 127（坏参数或不可执行；findings 不产生 exit 2）→ 按 COMMON-RULES §Layer 1 调用协议判 FAIL，先
     `cataforge doctor`
   - 命令不存在时 WARN 跳过，不阻塞
8. **[EVENT BATCH]** 通过 `--batch` 单次 stdin 管道一次性记录 4 条事件（phase_end → review_verdict →
   state_change → phase_start）:
   ```bash
   cataforge event log --batch <<'EOF'
   {"event":"phase_end","phase":"{当前阶段}","status":"approved","detail":"reviewer 通过"}
   {"event":"review_verdict","phase":"{当前阶段}","agent":"reviewer","status":"approved","detail":"审查通过"}
   {"event":"state_change","phase":"{新阶段}","detail":"{INSTRUCTION_FILE} 阶段更新: {旧阶段} → {新阶段}"}
   {"event":"phase_start","phase":"{新阶段}","detail":"进入{新阶段名}阶段"}
   EOF
   ```
9. **{INSTRUCTION_FILE} hygiene 强制门** — 在派发下一阶段 Agent 之前执行：
   ```bash
   cataforge claude-md check
   ```
   - exit 0 → 通过，继续 Step 10
   - exit 1（任一 `claude_md_limits` 阈值越界）→ **阻塞 Phase Transition**，向用户展示 stdout 的问题摘要并提供选项：
     1. 自动 compact：执行 `cataforge claude-md compact`，重新跑 `check`，PASS 后继续 Step 10
     2. 手动处理：暂停 Phase Transition，等待用户编辑 {INSTRUCTION_FILE} 后再次推进（再次推进时重新跑 Step 9）
   - 执行 compact 后追加 **[EVENT]** 记录：`cataforge event log --event state_change --phase {新阶段} --detail "claude-md compact applied at phase transition"`
   - 命令不存在时 WARN 跳过，不阻塞
10. **进入下一阶段** — 按 `framework.json#/workflow` 的 `execution_host` 分派：`subagent` →
    agent-dispatch 激活下一阶段 Agent；`inline` → 主线程承载该角色执行（见 §Inline Role Execution Protocol）。进入
    ui_design 且 {INSTRUCTION_FILE} §项目信息.设计工具=penpot 时，派发 ui-designer 前先执行 §Design-Tool
    Capability Gate。

> **关键**: 步骤 1-9 必须在步骤 10 之前全部完成，防止会话恢复时因状态未更新而误判阶段未完成。批量写入保证 4 条事件要么全部落盘要么全部失败，避免审计日志出现半截状态。

## {INSTRUCTION_FILE} 项目状态写入纪律
`{INSTRUCTION_FILE}` `§项目状态` 只承载恢复推进所需的实时状态。

- `当前阶段` / `下一步行动` / `当前Sprint`: 当前可执行状态。
- `上次完成`: 最近收口一句话，不列 PR、调试、升级链、已关闭问题。
- `已完成阶段`: 阶段枚举；`文档状态`: doc_type → status。
- 历史与证据写入 `docs/EVENT-LOG.jsonl`、`docs/reviews/`、`docs/changelog/`；需引用时只放短路径。
- `claude-md check` 在区总行数超 `max_state_section_lines` 或单行超 `max_state_bullet_chars` 时 FAIL；
  命中先外迁历史再继续推进。
- 状态表述必须 merge 后仍成立：不写「待 PR / 待 push / 待合并」等交付时态措辞；PR 号由 merge commit 承载，正文不追记。
- merge 后仅当状态块实质丢失或内容错误才补状态修正 PR；纯措辞过时不单独开 PR。
- 每槽位滚动覆盖：完成「当前」即用其替换「上次完成」旧值，再从「下一步」提一项补进「当前」；不追加历史。
- 每项一行，尽量指向 dev-plan 里程碑 / 任务编号。
- Backlog 明细进 docs/proposals/，`§项目状态` 的 `Backlog` 槽位仅留指向提案的短路径指针，不在状态区展开候选清单。

## Design-Tool Capability Gate
进入 ui_design 且设计工具=penpot 时，进入 ui-designer 角色前由 orchestrator 主线程门禁 MCP 可用性：

1. **探测** — 检查主线程工具表是否含 `mcp__penpot__*`。在表 → 再跑 `cataforge penpot status` 确认握手与插件连接（握手 Up ≠
   插件已连）；不在表 → 记为「工具未注册」。
2. **区分形态** — 「工具未注册」（MCP server 已声明但工具不在表，多为未预启用 / 未部署）与「连接失败 / 插件未连」是两类，分别向用户报告，不混为一谈。
3. **不静默降级** — 不可用时报告形态并给选项：「排查 MCP 后重试」/「降级为纯文本手工 ui-spec」。
4. **降级落真值** — 用户选降级时把设计工具落为 none（消除假信号），记 **[EVENT]**：
   `cataforge event log --event state_change --phase ui_design --detail "design_tool penpot→none: {未注册|连接失败}，降级纯文本流"`，
   再进入 ui-designer 角色。
5. **可用即继续** — 工具在表且 status 健康 → 正常进入 ui-designer 角色，penpot-bridge 操作生效。

## Inline Role Execution Protocol
`framework.json#/workflow` 中 `execution_host: inline` 的 phase（如发散性的 Phase 1/2），由 orchestrator
在主线程承载该角色执行而非派发子代理——发散阶段需多轮 user-interview / 头脑风暴 / 澄清，派发子代理为非交互执行体无法触达用户。

执行步骤（orchestrator 侧）:
1. **加载角色** — Read 目标 role 的 AGENT.md（角色定义 / Input·Output Contract / Anti-Patterns / skills）；
   承载期间以该角色身份决策、受其约束，不以 orchestrator 身份拍板内容
2. **发散澄清** — 直接用 research(user-interview / web-search) + AskUserQuestion 在主线程做多轮调研与澄清（不走
   needs_input 回传）；调研痕迹落 `docs/research/` research-note，澄清结论落产出文档「决策记录」段
3. **产出文档** — 执行该角色核心 skill（如 req-analysis / arc-design），经 context finalize 定稿（status=draft）；
   落盘后主线程仅保留 doc_id + ≤3 句摘要，不滞留全文
4. **写入边界自检** — 以该角色 AGENT.md `allowed_paths` 为基准跑 `git diff --name-only`，越界文件 `git checkout`
   回滚并记录（同 agent-dispatch §写入范围校验，宿主由子代理返回改为内联段结束）
5. **审查门禁仍派子代理** — 产出后照常派发 reviewer（`subagent`）执行门禁，保留审查独立性

> inline 承载不调用 agent-dispatch；新建文档"至少一轮用户确认"在主线程直接 AskUserQuestion 即满足，不再走 needs_input。

## Manual Review Checkpoint Protocol
阶段转换时，根据 MANUAL_REVIEW_CHECKPOINTS 常量（见 COMMON-RULES §框架配置常量）决定是否暂停等待用户确认。

**触发时机**: 文档状态变为 approved 且 orchestrator 即将进入下一 Phase 时。

**执行步骤**:
1. 读取 {INSTRUCTION_FILE} §全局约定 中的 `人工审查检查点` 字段（未配置则使用 MANUAL_REVIEW_CHECKPOINTS 默认值）
2. 判断当前转换是否命中检查点（各值触发时机见 COMMON-RULES §MANUAL_REVIEW_CHECKPOINTS 可选值）
3. 命中时，先产出与本次转换匹配的可视化并在摘要「已完成」行附产物路径——确定性 CLI 调用，
   不阻塞推进，数据源未就绪跳过不报错（同 §Sprint Review Protocol 可视化保底焊点语义）：
   - `post_doc_freeze`：PRD 冻结 → `cataforge viz trace --format mermaid -o docs/viz/trace.mmd`；
     ARCH / UI-SPEC 冻结 → `cataforge viz arch --format mermaid -o docs/viz/arch.mmd`
   - `pre_dev` → `cataforge viz tasks --format mermaid -o docs/viz/tasks.mmd`
   - `post_sprint` / `pre_deploy` → 复用 Sprint 收口 dashboard 产物路径

   随后使用 AskUserQuestion 向用户展示阶段摘要并确认。**当 checkpoint = `pre_deploy` 且
   framework.json `pre_deploy_demo_required: true`**（UI/web 类项目默认 true，纯后端服务
   默认 false）时，选项追加 demo 验证项；其它 checkpoint 用基础选项即可：

   基础选项（所有 checkpoint）:
   ```
   === 阶段转换确认 ===
   已完成: {当前阶段名} — {关键产出摘要}
   即将进入: {下一阶段名} — {预期工作概述}

   选项:
   1. 确认继续
   2. 暂停，我需要先审查产出
   3. 调整方向（进入 Change Request 流程）
   ```

   pre_deploy + demo_required=true 追加选项 4：
   ```
   4. 已亲自浏览器验证 ≥ {min_acs} 个核心 AC（必填项；未选不可推进）
   ```
   `min_acs` 取自 framework.json `pre_deploy_demo_min_acs`（默认 1）；用户必须选 4 才能进入 Phase 7，否则视为暂停。

   post_sprint 专用模板（当 checkpoint = `post_sprint` 时替换基础模板）:
   ```
   === Sprint {N} 完成确认 ===
   已完成任务: {Sprint 任务 ID 和名称列表}
   通过率: {passed}/{total}
   新增/变更功能: {本 Sprint 用户可感知的功能摘要}

   选项:
   1. 确认继续下一 Sprint
   2. 暂停，我需要手动验证功能
   3. 发现偏移，需要调整需求（进入 Change Request）
   ```
   当本 Sprint 包含 `user_facing_critical_path: true` 的任务时，追加选项 4：
   ```
   4. 已手动验证核心功能正常工作
   ```
4. 用户选择"确认继续"（或 pre_deploy demo_required=true 时选项 4）→ 正常推进
5. 用户选择"暂停" → orchestrator 等待用户后续指令（不自动推进）
6. 用户选择"调整方向" → 进入 Change Request Protocol

**不命中时**: 直接按现有逻辑自动推进，无额外交互。

## Recovery Protocols 触发索引
命中下列征兆时，Read [`ORCHESTRATOR-RECOVERY-PROTOCOLS.md`](ORCHESTRATOR-RECOVERY-PROTOCOLS.md)
按对应协议处置：

| 触发征兆 | 协议 |
|---------|------|
| TDD REFACTOR 子代理返回 `rolled-back` | §Rolled-back Recovery Protocol |
| TDD 子代理返回 blocked 且含 `<questions>` | §TDD Blocked Recovery Protocol |
| 子代理返回无 `<agent-result>` 且兜底无法推断状态（process 死） | §Agent Crash Recovery Protocol |
| truncation 征兆（100+ tools / 100K+ tokens / 5min+ / 无 `<agent-result>`）但已有未提交 artifact | §Sub-Agent Truncation Recovery Protocol |

## Parallel Task Dispatch Protocol
当 Phase 5 development 阶段一次推进多个任务时，orchestrator 优先按依赖图并行调度，墙钟时间从 N 倍单任务降到约 1 倍最长依赖链。

**适用前提**:
- task-dep-analysis 已生成 `sprint_groups`（同组无依赖；上游 sprint_group 全部完成后才进入下一组）
- 同一 sprint_group 内的任务都已通过 Step 1（任务上下文已提取）

**validation 任务调度**:
当 Sprint 中包含 `task_kind: validation` 的任务时:
1. validation 任务**不进入 TDD 流程**，不调度 test-writer / implementer
2. orchestrator 在该任务的所有前置任务完成后，通过 AskUserQuestion 向用户展示验证清单
3. 用户选项:
   - "全部通过": 任务状态 → done
   - "发现问题": 用户描述问题 → 进入 Change Request Protocol
   - "暂时跳过": 任务状态 → deferred，不阻塞后续 Sprint
4. validation 任务不计入 `SPRINT_REVIEW_MICRO_TASK_COUNT` 阈值（它本身已包含用户确认）

**并行规则**:
1. **同 sprint_group 任务并行 RED/GREEN/LIGHT**：在**单条主线程消息内**通过 agent_dispatch 工具发出多个调度调用，并发上限 =
   `min(sprint_group 任务数, 3)`。批次完成后才进入下一阶段，避免阶段交叉
2. **批次内禁止并行 REFACTOR**：refactor 改动源码冲突大；REFACTOR 必须串行（按 sprint_group 内的字典序）
3. **同模块批量化优先于并行调度**：当 sprint_group 内 ≥2 个任务共享同一 arch#§2.M-xxx 时，先尝试合并为一次 test-writer 调用（见
   tdd-engine §RED 批量化），剩余任务再走并行调度
4. **回退条件**：若并行调度任一子代理返回 blocked / needs_input → 取消同批次未启动的调度（已启动的等待返回），降级为串行模式重跑该批次

**事件记录**:
- **[EVENT BATCH]** 一次性记录批次启动（每个调度对应一条 agent_dispatch，由 PreToolUse hook 自动写入）
- 批次完成后 orchestrator 写入 `dispatch_batch_end` 标记到 detail（不新增 event 类型，复用 `state_change`）

**安全护栏**:
- 文件系统竞态：同 sprint_group 任务的 deliverables 必须无路径重叠（已由 task-decomp 在 Phase 4 保证），orchestrator
  在派发前再做一次 deliverables 路径并集 vs 单任务路径集合大小校验，命中冲突立即降级串行
- maxTurns 截断：每个并行子代理独立计数，互不影响

## Sprint Review Protocol
当Sprint所有任务完成（dev-plan§1 Sprint表中所有任务状态=done）时:

**微型 Sprint 短路判定** (Step 0):
若同时满足以下条件则**跳过 sprint-review**，直接视为 approved:
- 本 Sprint 任务数 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT`
- 所有需即时 code-review 的任务（`security_sensitive` / `user_facing_critical_path` /
  `consumer_components` 非空）结论为 approved，且延迟任务的 implementer self-report 无
  `refactor_needed=true`

短路时处理:
1. 对延迟任务（未经即时 per-task code-review 的任务）的 impl_files 范围跑一次
   `code-review scan --focus complexity,duplication,coupling`（Layer 1 确定性兜底，同 tdd-engine
   Sprint 级审查的审计 scan）；exit 1 → 取消短路，转正常流程
2. 在 {INSTRUCTION_FILE} 当前 Sprint 字段追加注记 `sprint-review skipped (micro sprint)`
3. **[EVENT]** 记录跳过事件:
   ```bash
   cataforge event log --event review_verdict --phase development --agent orchestrator --status approved --detail "sprint-review skipped (micro sprint)"
   ```
4. 直接进入下一 Sprint 或 Phase 6

**正常流程** (不满足短路条件时):
1. 通过 agent-dispatch 激活 reviewer (task_type=new_creation, skill=sprint-review)
2. 传入: dev-plan路径, Sprint编号, 已有CODE-REVIEW报告路径（仅即时审查的任务）, arch文档路径。本 Sprint 中未经 per-task
   code-review 的延迟任务由 sprint-review 承担等价审查（Batch Code-Review）：reviewer 在报告的 §per-task L2
   维度表中逐任务覆盖 structure / error-handling / test-quality / security 维度（复用 §merged-review
   的维度表格式），这些任务不需要独立 CODE-REVIEW-T-NNN 文件
3. reviewer执行sprint-review skill，产出 `SPRINT-REVIEW-s{N}-r{M}.md`
4. 结果处理:
   - **approved** → 更新{INSTRUCTION_FILE} Sprint字段，进入下一Sprint（或全部Sprint完成后进入Phase 6）
   - **approved_with_notes** → 按 Approved-with-Notes Protocol 处理
   - **needs_revision** → 从SPRINT-REVIEW报告中提取标记为CRITICAL/HIGH的任务ID，仅这些任务重新进入TDD（已通过的任务保持done状态不变）
5. Sprint Review的needs_revision不计入Phase级needs_revision计数（独立跟踪）

**Sprint 收口可视化保底焊点**（短路与正常路径均适用）: Sprint 视为 approved 后，运行
`cataforge viz dashboard -o docs/viz/dashboard.html` 产出聚合健康度看板（覆盖矩阵 / 追溯链 / 腐化趋势）并向用户提示产物路径。
全部 Sprint 完成、进入 Phase 6 前同样产出，作为开发收口的保底可视化。该步骤是确定性 CLI 调用，不阻塞推进；数据源未就绪时
`cataforge viz status` 自陈空视图，跳过不报错。

## Change Request Protocol
当orchestrator检测到用户输入为变更请求（而非流程推进指令）时:
1. 通过 change-guard skill 分析变更（orchestrator直接执行，无需agent-dispatch）；`<change-analysis>` XML
   格式定义见 change-guard SKILL.md §Step 5
2. 向用户展示 `<change-analysis>` 结果，提供选项:
   - "确认执行": 按action路由执行
   - "调整范围": 用户修改变更描述后重新分析
   - "取消": 不执行变更
3. 根据 action 路由:
   - **proceed** → 直接在当前阶段执行变更（不触发文档修订）
   - **amend_then_proceed** → 通过agent-dispatch调度affected_docs的原作者Agent(task_type=amendment)修订文档，
     每个文档修订后经reviewer审核，全部通过后执行变更
   - **cascade_amendment** → 从最上游affected doc开始逐级修订: PRD → ARCH → UI-SPEC(如适用) → DEV-PLAN，
     每级修订+审核后才进入下级

### cascade_amendment 中断规则
cascade_amendment 中任一文档修订触发人工介入阈值（needs_revision 计数 N≥2，见 §Revision Protocol）:
1. 暂停后续文档修订，不继续下游文档
2. 已修订的上游文档保持 draft 状态（不标记 approved）
3. 向用户报告失败点和已完成的修订范围，提供选项:
   - "继续修复失败文档": 进入 Revision Protocol 修复当前文档
   - "回滚所有修订": `git checkout -- docs/{affected_dirs}` 恢复所有本轮修订的文档
4. 回滚后变更请求状态重置，用户可调整范围后重新提交

变更完成后先按 §Phase Transition Protocol Step 6 执行 reconcile 收口（漂移按 Step 6 归因处置），再回到原阶段继续执行。
Amendment 与 Revision 的区别: Revision由reviewer发起（修复问题），Amendment由用户发起（适应变更），
但执行机制复用agent-dispatch和reviewer审核流程。

> 子代理收到 `task_type=amendment` 后的修订步骤见 `{RULES_DIR}/SUB-AGENT-PROTOCOLS.md §task_type=amendment 变更修订流程`。

## needs_revision 计数规范
`needs_revision(N)` 中的 N 为本阶段累计返工次数，格式为 `needs_revision(2)` 而非独立字段。
- N=1: 正常修订流程（增量审查模式）
- N>=2: 暂停自动推进，请求人工介入（同时触发 [`ORCHESTRATOR-META-PROTOCOLS.md §Adaptive Review Protocol`](ORCHESTRATOR-META-PROTOCOLS.md#adaptive-review-protocol)）

## {INSTRUCTION_FILE} Update Template
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
  <!-- changelog 由 devops 产出但不纳入门禁追踪 --> <!-- allow-design-residue: downstream-claude-template -->
```

> 状态值合法集: 未开始 | draft | review | approved | needs_revision | needs_revision(N) | N/A
