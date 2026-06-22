# 走查执行协议

本文件是 framework-walkthrough §执行步骤 的展开，给出隔离沙盒搭建、各执行模式驱动、Phase Transition 一致性门观察与 `--depth full` 探针程序的操作细节。所有命令用平台无关的 `cataforge` CLI；驱动逻辑用能力标识符描述，由宿主平台的 agent 调度能力（`agent_dispatch`）落地。

驱动覆盖面以 [`runtime-flow-map.md`](runtime-flow-map.md) 的五类路径为准（初始化 / 核心执行链路 / 分支 / 异常 / 终止清理）；本文件只给「怎么驱动 / 怎么探针」，不复制路径枚举。`--depth smoke`（缺省）只跑 §2 主干驱动；`--depth full` 在主干基础上追加 §6 探针。

## 1. 隔离沙盒的必要性

走查会真实写出 `docs/` 文档、`PROJECT-STATE`、`docs/EVENT-LOG.jsonl`、KG store、`docs/reviews/*`。若在宿主真实项目根跑，会覆写真实资产、污染自学习闭环。因此走查**必须**在一个与宿主隔离、且被版本控制忽略的沙盒目录内进行。

### 1.1 搭建沙盒

1. 选沙盒路径：缺省 `walkthrough-sandbox/<platform>-<mode>-<时间戳>/`（相对宿主仓库根；时间戳 `yyyyMMdd-HHmmss`，使并发/重跑各占独立目录）。确保该路径被 `.gitignore` 覆盖（缺则先补一行）。
2. 目标目录非空时**另起新 run-id 或先 `--clean` 清空**再用——非空目录直接复用会让两次走查互相写入对方产物、归因困难。新建空目录并进入（后续所有命令的 cwd = 沙盒目录）。
3. 初始化框架资产：`cataforge setup`（按 `cataforge setup --help` 确认平台参数；若 setup 不接受平台参数，则 `cataforge deploy --platform <platform>`）。目标是在沙盒内得到独立的 `.cataforge/` 与目标平台的部署产物。
4. 健全性确认：`cataforge doctor` 应通过；`framework.json#/version` 非 `0.0.0-template`。

### 1.2 跨平台差异的吸收点

沙盒搭建与驱动协议对四端**完全一致**；平台差异由 deployer 与降级策略吸收。`--platform` 只改变部署出的原生产物形态（命令/agent/hook 配置），不改变走查步骤。在非 Claude-Code 平台上，「主线程扮演 orchestrator」由该平台的等价会话承担，子代理调度走该平台 `agent_dispatch` 的降级路径。

走查驱动**必须由主线程内联承载**：所有 `cataforge` 命令在主线程当前 cwd（= 沙盒目录）执行。不得把驱动整体委派给一个子代理——子代理在宿主 cwd 运行，会绕开沙盒、写进真实项目根。子代理仅用于框架要求的 agent 角色调度（如 TDD 子代理），其工作目录须显式指向沙盒。

## 2. 按执行模式驱动

三种模式的阶段集合、文档产出、TDD 档位、门禁差异以 COMMON-RULES §执行模式矩阵 为准；本节只给走查驱动顺序。

### 2.1 agile-lite（缺省）

最能在单轮内触达主干：

1. **planning**：起 start-orchestrator → Bootstrap，选 `agile-lite`。产出 prd-lite + arch-lite + dev-plan-lite（各 ≤100 行）。喂入 `example-project.md` 的功能项 / 架构契约 / 任务分解。
2. **doc-review**：对三份 lite 文档跑 Layer 1（经 `cataforge skill run doc-review -- <doc-type> <path>`）；`<doc-type>` 取文档 front-matter 的 `doc_type` 字面值——lite 文档仍为 `prd`/`arch`/`dev-plan`，**非** `prd-lite`；传错会落到「未知类型仅通用检查」而漏掉 typed 检查。按 `DOC_REVIEW_L2_SKIP_*` 判断是否短路 Layer 2。
3. **development**：按 dev-plan-lite 的 T-001/T-002/T-003 跑 TDD light（RED+GREEN 合并）。T-001 是纯逻辑表驱动 AC，最适合作为 TDD 主验证。
4. **code-review**：GREEN 后对核心跑 code-review；按 `CODE_REVIEW_L2_SKIP_*` 判断短路。
5. **收敛**：development 全部任务 approved 且评审通过即结束（任务数 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT` 时跳过 sprint-review）。deployment 标 N/A。

### 2.2 agile-prototype（更快更浅）

Phase 1~4 合并为单一 `brief.md`（≤200 行），implementer 主线程一次性写测试+实现，跳过 RED/GREEN/REFACTOR 子代理调度。用于验证「最小路径是否通」，但不单独考察架构阶段与 TDD 三段拆分。

### 2.3 standard（最全最重）

7 阶段全跑，产出 PRD + ARCH +（可选 UI-SPEC）+ DEV-PLAN + 评审报告。TDD 默认 light，T-001 若预估 LOC 超 `TDD_LIGHT_LOC_THRESHOLD` 或标 `security_sensitive` 则升 standard。用于最大化覆盖；代价是单轮难收敛，仅在需要深度走查时选用。

### 2.4 Phase Transition 一致性门观察（所有模式）

每次 reviewer approved 后进入下一阶段，都会跑 `ORCHESTRATOR-PROTOCOLS §Phase Transition Protocol` 的 8 步（路径图 C-5a~C-5g）。这是走查最易漏看的过程信号——文档「最终产出了」不代表一致性门「跑过了」。逐子步盯：

- `cataforge context validate`（C-5b 依赖新鲜度）：上游 approved 后下游是否被标 stale_deps。
- `cataforge context reconcile`（C-5c 一致性守门）：图后端启用时漂移是否被捕获、remediation 方向（export/ingest/manual）是否匹配；逐文档 triage state 与 per-doc_type 对称 diff 明细经 `cataforge context reconcile --json` 取得（门禁结论取文档级 triage，对称 diff 为诊断）。`context.mode = markdown` 下退化为 docs-index 完整性校验（无图后端），其结论按索引有效性读，记为正常而非缺陷。
- `cataforge skill run doc-consistency`（C-5d）：**至少 2 个业务文档 approved 后**（即 Phase 2+ 转换）才触发；agile-lite 在 arch-lite approved 进 dev_planning 时首次满足。exit 0/2 继续、exit 1 给分支选项。
- EVENT BATCH（C-5e）：`docs/EVENT-LOG.jsonl` 是否一次性出现 phase_end→review_verdict→state_change→phase_start 四条，无半截状态。
- `cataforge claude-md check`（C-5f hygiene 门）：阈值越界须**阻塞**转换并给 compact 选项，不能 WARN 放行。

任一门「该跑没跑 / 该阻塞没阻塞 / 静默降级」都是 framework finding；命令不存在而 WARN 跳过须显式记录，不可读作通过。

## 3. 驱动时的代答约定

沙盒内为保持单轮闭环，遇到 MANUAL_REVIEW_CHECKPOINTS 或 agent 的 `needs_input` 时，由走查者依据 `example-project.md` 的既定目标直接代答，并把「此处需要人工输入」本身记为一个观察点（用于评估流程的交互负担）。不得因代答而跳过门禁的实际执行。

## 4. 单轮预算保护

若某阶段反复 `needs_revision` 或 `blocked` 超过两轮仍不收敛，停止驱动，把卡点连同原始输出记为 `framework`/`blocked` 类 finding，转入 Step 6 出报告——走查的产出是「跑的过程暴露了什么」，不是「必须把示例做完」。

## 5. 阶段产物硬门槛（phase status）

每跨完一个阶段，立即在沙盒 cwd 跑 `cataforge phase status` 校验当前阶段应有产物：当前阶段非占位符、期望 `docs/<doc_type>(-lite).md` 存在且已 index、有 `phase_start` 事件、文档状态 ≠ 未开始。**退出非 0 即判该阶段 `blocked`**，把 `phase status` 输出连同卡点记为 `framework`/`blocked` 类 finding 并停止推进。此门槛把「框架已部署」与「阶段真被驱动」分开——委派子代理只部署不驱动时（`docs/` 空、无 `EVENT-LOG`、当前阶段仍占位）会在此处暴露，不可凭「最终有没有文档」事后补判。

## 6. 分支与异常路径探针程序（`--depth full`）

`--depth smoke` 只跑主干，分支/异常路径多为 not-reached。`--depth full` 在 happy path 收敛后，对下列**可确定性触发**的路径各做一次最小扰动探针；每个探针是一次有界观察，触发并记录该路径行为后即恢复主干，不展开成另一条完整 SDLC。扰动素材见 [`example-project.md`](example-project.md) §探针扰动。

| 路径 | 探针（最小扰动） | 看什么 |
|------|-----------------|--------|
| B-3 Approved-with-Notes | 在某文档留 ≥1 个 MEDIUM/LOW 级瑕疵（如缺一条非功能约束），让 reviewer 出 approved_with_notes | 4 选项是否展示、选项 4（全量 inline-fix）门控条件是否正确 |
| B-4 Sprint Review 短路 | 用 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT` 个任务的示例（temperature-converter 默认 3 个即满足） | 是否跳过 sprint-review 并记 skip 事件 |
| B-5 Parallel Dispatch | dev-plan 里让 T-002 / T-003 互不依赖、同 sprint_group | 是否单消息批量调度、deliverables 路径冲突是否降级串行 |
| B-6 Change Request | development 前向主线程提交一句变更（如「F-003 改保留 1 位小数」） | change-guard 是否分析、action 路由（proceed/amend/cascade）是否正确 |
| B-7 模式回退 | agile-lite 下故意把 prd-lite 写到 >150 行 | 是否提示升档、是否误自动改写模式字段 |
| B-12 skippable N/A | 确认 ui_design/testing/deployment 标 N/A | 路由是否跳过、不误判缺产物 |
| E-1 Interrupt-Resume | 起 inline 角色时漏喂一项必填输入（如不给目标精度），诱发澄清 | inline 角色直接 AskUserQuestion（不走 needs_input）；派发子代理才经 needs_input 回传 |
| E-2 Revision | 让首版文档缺一个 CRITICAL/HIGH 必备项（如 arch 缺 API 契约），诱发 needs_revision | 是否调 task_type=revision、增量审查是否只审 diff + 上轮高危维度、needs_revision(N) 是否累计 |

机会观察类（路径图标 `O`：E-3 rolled-back / E-4 TDD blocked / E-5 crash / E-6 truncation / E-7 cascade 中断 / E-9 Layer 1 FAIL / B-8~B-11 一致性门分支）**不做人为破坏注入**——强行制造崩溃会偏离真实行为、污染归因。它们若在 `D`/`P` 路径推进中自然出现即记录，否则账本标 not-reached 并写明「单轮未自然触发」。
