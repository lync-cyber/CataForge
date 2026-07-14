# 走查执行协议

本文件是 framework-walkthrough §执行步骤 的展开，给出隔离沙盒搭建、各执行模式驱动、Phase Transition 一致性门观察与 `--depth full` 探针程序的操作细节。所有命令用平台无关的 `cataforge` CLI；驱动逻辑用能力标识符描述，由宿主平台的 agent 调度能力（`agent_dispatch`）落地。

驱动覆盖面以 [`runtime-flow-map.md`](runtime-flow-map.md) 的五类路径为准（初始化 / 核心执行链路 / 分支 / 异常 / 终止清理）；本文件只给「怎么驱动 / 怎么探针」，不复制路径枚举。`--depth smoke`（缺省）只跑 §2 主干驱动；`--depth full` 在主干基础上追加 §6 探针。

## 1. 隔离沙盒的必要性

走查会真实写出 `docs/` 文档、`PROJECT-STATE`、`docs/EVENT-LOG.jsonl`、KG store、`docs/reviews/*`。若在宿主真实项目根跑，会覆写真实资产、污染自学习闭环。因此走查**必须**在一个与宿主隔离、且被版本控制忽略的沙盒目录内进行。

### 1.1 搭建沙盒

1. 选沙盒路径：缺省 `walkthrough-sandbox/<platform>-<mode>-<时间戳>/`（相对宿主仓库根；时间戳 `yyyyMMdd-HHmmss`，使并发/重跑各占独立目录）。确保该路径被 `.gitignore` 覆盖（缺则先补一行）。创建前校验 shell 当前 cwd == 仓库根，或恒以仓库根绝对路径拼接沙盒路径。
2. 目标目录非空时**另起新 run-id 或先 `--clean` 清空**再用——非空目录直接复用会让两次走查互相写入对方产物、归因困难。新建空目录并进入（后续所有命令的 cwd = 沙盒目录）。
3. 初始化框架资产：`cataforge setup`（按 `cataforge setup --help` 确认平台参数；若 setup 不接受平台参数，则 `cataforge deploy --platform <platform>`）。目标是在沙盒内得到独立的 `.cataforge/` 与目标平台的部署产物。
4. 健全性确认：`cataforge doctor` 应通过；`framework.json#/version` 非 `0.0.0-template`。
5. 健全性失败处置：保留 `cataforge doctor` 的原始输出，按其 remediation 修复并复跑一次；仍非零则停止 Bootstrap，覆盖账本标 `I-6=finding`、`E-10=driven`，其余未执行路径统一标 `not-reached: bootstrap health gate blocked`，转 Step 6 出报告。

### 1.2 跨平台差异的吸收点

沙盒搭建与驱动协议对四端**完全一致**；平台差异由 deployer 与降级策略吸收。`--platform` 只改变部署出的原生产物形态（命令/agent/hook 配置），不改变走查步骤。在非 Claude-Code 平台上，「主线程扮演 orchestrator」由该平台的等价会话承担，子代理调度走该平台 `agent_dispatch` 的降级路径。

走查驱动**必须由主线程内联承载**：所有 `cataforge` 命令在主线程当前 cwd（= 沙盒目录）执行。不得把驱动整体委派给一个子代理——子代理在宿主 cwd 运行，会绕开沙盒、写进真实项目根。子代理仅用于框架要求的 agent 角色调度（如 TDD 子代理），其工作目录须显式指向沙盒。

## 2. 按执行模式驱动

三种模式的阶段集合、文档产出、TDD 档位、门禁差异以 COMMON-RULES §执行模式矩阵 为准；本节只给走查驱动顺序。

### 2.1 standard（缺省）

7 阶段全跑，门禁、人工检查点与 testing 阶段覆盖面最大：

1. **planning (Phase 1)**：起 start-orchestrator → Bootstrap，选 `standard`。product-manager 产 PRD（喂 `example-project.md` 功能项）→ doc-review（Layer 1 + Layer 2 强制，无 lite 短路）。
2. **architecture (Phase 2)**：architect 产 ARCH（喂架构契约 C-001/C-002/API-001）→ doc-review。此转换起 doc-consistency（C-5d）首次满足触发条件。
3. **ui_design (Phase 3)**：缺省 CLI 示例标 N/A 跳过——顺带确认 B-12 skippable 路由不误判缺产物。`--example temperature-converter-ui` 时真驱动（B-13）：design_tool=none 走 ui-designer 纯文本流产 ui-spec → doc-review；要连带观察 Capability Gate 降级（B-14）则 Bootstrap 时设计工具选 penpot。
4. **dev_planning (Phase 4)**：tech-lead 产 DEV-PLAN（喂任务分解，task-decomp / task-dep-analysis 拆卡与依赖建模）→ doc-review；转入 development 前命中 `pre_dev` 人工检查点，按 §3 代答并记录交互负担。
5. **development (Phase 5)**：按 T-001/T-002/T-003 跑 TDD（缺省 light；升档观察经 full 深度的 C-6 探针）+ code-review 分级触发（T-001 带 `consumer_components` 走即时审查且恒命中 L2 豁免全跑；T-002/T-003 延迟到 sprint-review 侧，见 B-4/B-15）。Sprint 收口后确认 C-9 viz dashboard 保底焊点（§2.5）。
6. **testing (Phase 6)**：qa-engineer 做集成/E2E 补充与 TEST-REPORT——观察 testing 阶段编排与 verdict 语义（approved / conditional_release 的 blocking_conditions 阻塞）。
7. **deployment (Phase 7)**：标 N/A。`pre_deploy` 检查点在 deployment 被跳过时是否仍触发，协议未明定——实际行为（触发/不触发/报错）本身即观察点，如实入账本；若触发则按 §3 代答。

相对 lite 档的覆盖增量：全量文档 Layer 2 门禁、pre_dev / pre_deploy / post_sprint 检查点、testing 阶段、TDD 分档判定。代价是单轮更重；追求快速冒烟时显式降 `--mode agile-lite`。

### 2.2 agile-lite（快速档）

单轮最易收敛、触达主干，适合快速冒烟：

1. **planning**：起 start-orchestrator → Bootstrap，选 `agile-lite`。产出 prd-lite + arch-lite + dev-plan-lite（各 ≤100 行）。喂入 `example-project.md` 的功能项 / 架构契约 / 任务分解。
2. **doc-review**：对三份 lite 文档跑 Layer 1（经 `cataforge skill run doc-review -- <doc-type> <path>`）；`<doc-type>` 取文档 front-matter 的 `doc_type` 字面值——lite 文档仍为 `prd`/`arch`/`dev-plan`，**非** `prd-lite`；传错会落到「未知类型仅通用检查」而漏掉 typed 检查。按 `DOC_REVIEW_L2_SKIP_*` 判断是否短路 Layer 2。
3. **development**：按 dev-plan-lite 的 T-001/T-002/T-003 跑 TDD light（RED+GREEN 合并）。T-001 是纯逻辑表驱动 AC，最适合作为 TDD 主验证。
4. **code-review**：GREEN 后对核心跑 code-review；按 `CODE_REVIEW_L2_SKIP_*` 判断短路。
5. **收敛**：development 全部任务 approved 且评审通过即结束（任务数 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT` 时跳过 sprint-review）。deployment 标 N/A。

### 2.3 agile-prototype（更快更浅）

Phase 1~4 合并为单一 `brief.md`（≤200 行），implementer 主线程一次性写测试+实现，跳过 RED/GREEN/REFACTOR 子代理调度。用于验证「最小路径是否通」，但不单独考察架构阶段与 TDD 三段拆分。

### 2.4 Phase Transition 一致性门观察（所有模式）

每次 reviewer approved 后进入下一阶段，都会跑 `ORCHESTRATOR-PROTOCOLS §Phase Transition Protocol` 的 8 步（路径图 C-5a~C-5g）。这是走查最易漏看的过程信号——文档「最终产出了」不代表一致性门「跑过了」。逐子步盯：

- `cataforge context validate`（C-5b 依赖新鲜度）：上游 approved 后下游是否被标 stale_deps。
- `cataforge context reconcile`（C-5c 一致性守门）：图后端启用时漂移是否被捕获、remediation 方向（export/ingest/manual）是否匹配；逐文档 triage state 与 per-doc_type 对称 diff 明细经 `cataforge context reconcile --json` 取得（门禁结论取文档级 triage，对称 diff 为诊断）。`context.mode = markdown` 下退化为 docs-index 完整性校验（无图后端），其结论按索引有效性读，记为正常而非缺陷。
- `cataforge skill run doc-consistency`（C-5d）：**至少 2 个业务文档 approved 后**（即 Phase 2+ 转换）才触发；standard 在 ARCH approved 进 ui_design 时、agile-lite 在 arch-lite approved 进 dev_planning 时首次满足。exit 0/2 继续、exit 1 给分支选项。
- EVENT BATCH（C-5e）：`docs/EVENT-LOG.jsonl` 是否一次性出现 phase_end→review_verdict→state_change→phase_start 四条，无半截状态。
- `cataforge claude-md check`（C-5f hygiene 门）：阈值越界须**阻塞**转换并给 compact 选项，不能 WARN 放行。

任一门「该跑没跑 / 该阻塞没阻塞 / 静默降级」都是 framework finding；命令不存在而 WARN 跳过须显式记录，不可读作通过。

### 2.5 Sprint 收口可视化保底观察（所有模式）

Sprint 视为 approved 后（含 micro 短路路径）与全部 Sprint 完成进 testing 前，orchestrator 应确定性跑 `cataforge viz dashboard -o docs/viz/dashboard.html`（路径 C-9）。盯三点：焊点是否真被执行、产物是否落地、沙盒小项目数据源不全时降级是否显式（tile 显示 `—` 附 `run:` 指引 / `viz status` 自陈空视图跳过）——焊点静默缺席或数据缺失被读作正常都是 framework finding。

## 3. 驱动时的代答约定

沙盒内为保持单轮闭环，遇到 MANUAL_REVIEW_CHECKPOINTS 或 agent 的 `needs_input` 时，由走查者依据 `example-project.md` 的既定目标直接代答，并把「此处需要人工输入」本身记为一个观察点（用于评估流程的交互负担）。不得因代答而跳过门禁的实际执行。向审查/测试类子代理派发时，返回 schema 的 verdict 枚举须携带 COMMON-RULES 的完整集合（含 approved_with_notes / conditional_release），不得按预期结果裁剪。

## 4. 单轮预算保护

若某阶段反复 `needs_revision` 或 `blocked` 超过两轮仍不收敛，停止驱动，把卡点连同原始输出记为 `framework`/`blocked` 类 finding，转入 Step 6 出报告——走查的产出是「跑的过程暴露了什么」，不是「必须把示例做完」。

## 5. 阶段产物硬门槛（phase status）

每跨完一个阶段，立即在沙盒 cwd 跑 `cataforge phase status` 校验当前阶段应有产物：当前阶段非占位符、期望 `docs/<doc_type>(-lite).md` 存在且已 index、有 `phase_start` 事件、文档状态 ≠ 未开始。**退出非 0 即判该阶段 `blocked`**，把 `phase status` 输出连同卡点记为 `framework`/`blocked` 类 finding 并停止推进。此门槛把「框架已部署」与「阶段真被驱动」分开——委派子代理只部署不驱动时（`docs/` 空、无 `EVENT-LOG`、当前阶段仍占位）会在此处暴露，不可凭「最终有没有文档」事后补判。

## 6. 分支与异常路径探针程序（`--depth full`）

`--depth smoke` 只跑主干，分支/异常路径多为 not-reached。`--depth full` 在 happy path 收敛后，对下列**可确定性触发**的路径各做一次最小扰动探针；每个探针是一次有界观察，触发并记录该路径行为后即恢复主干，不展开成另一条完整 SDLC。扰动素材见 [`example-project.md`](example-project.md) §探针扰动。

探针通用规则：

- **终止点**：每个探针以「目标行为被观察到」为收束点。可能连锁展开的探针（如 B-6 被路由为 cascade_amendment 会触发 PRD→ARCH→DEV-PLAN 逐级修订）在路由/选项**展示**后选「取消/不执行」收束——路由执行本身记 not-reached 并注明，不让单个探针横向吃掉主干预算。
- **判级依赖型**（B-3 / E-2 / E-1）：结果取决于 reviewer/agent 的运行时判断（判级、是否提问），未命中预期 verdict 时账本记 not-reached: 判级偏离，不重试死磕。

| 路径 | 探针（最小扰动） | 看什么 |
|------|-----------------|--------|
| B-3 Approved-with-Notes | 在某文档留 ≥1 个 MEDIUM/LOW 级瑕疵（如缺一条非功能约束），让 reviewer 出 approved_with_notes | 4 选项是否展示、选项 4（全量 inline-fix）门控条件是否正确 |
| B-1 模式三分叉 | 单轮不适用——须另起 `--mode` 重跑对比阶段集合/文档产出差异；单轮账本记 not-reached: 需多轮 | 跨模式差异是否符合执行模式矩阵 |
| B-4 Sprint Review 短路 | 仅 CLI 示例（3 任务恰 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT`）；UI 示例 4 任务走 B-15 正常路径 | 是否跳过 sprint-review 并记 skip 事件 |
| B-15 sprint-review 正常路径 | 零扰动——UI 示例 4 任务自然命中 | Batch Code-Review 是否逐任务覆盖延迟任务、needs_revision 是否只回炉 CRITICAL/HIGH |
| B-5 Parallel Dispatch | dev-plan 里让 T-002 / T-003 互不依赖、同 sprint_group | 是否单消息批量调度、deliverables 路径冲突是否降级串行 |
| B-6 Change Request | development 前向主线程提交一句变更（如「F-003 改保留 1 位小数」） | change-guard 是否分析、action 路由（proceed/amend/cascade）是否正确 |
| B-7 模式回退 | agile-lite 下故意把 prd-lite 写到 >150 行（仅 `--mode agile-lite` 可触发；standard 下账本标 not-reached: 模式不适用） | 是否提示升档、是否误自动改写模式字段 |
| B-12 skippable N/A | 确认 ui_design/testing/deployment 标 N/A | 路由是否跳过、不误判缺产物 |
| B-13 ui_design 真驱动 | 改用 `--example temperature-converter-ui`（非扰动，example 选择） | 纯文本 ui-spec 流是否顺畅、UI 保真 AC 是否断言渲染/计算效果而非字面、无渲染证据时是否 conditional_release 而非 `[ENV-LIMITATION]` 豁免 |
| B-14 Capability Gate 降级 | Bootstrap 设计工具选 penpot（沙盒无 penpot MCP） | 「工具未注册」vs「连接失败」是否分开报告、降级是否落真值 design_tool→none 并记 state_change EVENT、有无静默降级 |
| E-1 Interrupt-Resume | 派发 subagent 阶段（dev_planning tech-lead）时漏喂 Sprint 划分偏好，诱发 needs_input 回传（inline 阶段的 AskUserQuestion 澄清不属 E-1；判级依赖型） | needs_input → continuation 重启是否成立、每阶段 2 轮上限是否生效 |
| C-6 TDD 升档 | dev-plan 阶段把 T-003 标 `security_sensitive: true` | 是否升 standard 档（RED/GREEN 分离）、是否触发即时 code-review 且强制 Layer 2；REFACTOR 未命中 `TDD_REFACTOR_TRIGGER` 记 not-reached |
| E-2 Revision | 让首版文档缺一个 CRITICAL/HIGH 必备项（如 arch 缺 API 契约），诱发 needs_revision | 是否调 task_type=revision、增量审查是否只审 diff + 上轮高危维度、needs_revision(N) 是否累计 |

机会观察类（路径图标 `O`：E-3 rolled-back / E-4 TDD blocked / E-5 crash / E-6 truncation / E-7 cascade 中断 / E-9 Layer 1 FAIL / B-8~B-11 一致性门分支）**不做人为破坏注入**——强行制造崩溃会偏离真实行为、污染归因。它们若在 `D`/`P` 路径推进中自然出现即记录，否则账本标 not-reached 并写明「单轮未自然触发」。
