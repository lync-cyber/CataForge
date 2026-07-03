---
name: feature-walkthrough
description: "功能走查 — 对交付项目的功能实现做验收式动态走查，两层正交判定：①功能是否兑现 spec（missing/drift/bug/pass）；②代码本身是否健康（复用 COMMON-RULES §统一问题分类体系的 code category）。用真实数据路径起真实服务复现，专捞门禁全绿仍漏的跨模块集成缝隙。当项目功能交付后需验收、Sprint 发布前做功能级复核、或用户要求走查某功能域时使用。与 framework-walkthrough 动静对偶：后者在沙盒自测框架 SDLC，本 skill 验收交付项目的功能实现。"
argument-hint: "<功能域|页面|spec条目引用> [--scope <dir>] [--round <N>]"
suggested-tools: file_read, file_glob, file_grep, shell_exec, agent_dispatch, user_question
depends: [code-review, context]
disable-model-invocation: false
user-invocable: true
record-to-event-log: true
---

# 功能走查 (feature-walkthrough)

## 能力边界

- 能做: 按 spec（prd/arch/ui-spec/dev-plan 的功能条目）对交付实现做逐条符合性判定；对走查范围内代码做健康度扫描（可复用 code-review scan 的机检 probe）；用真实数据路径启动真实服务动态复现，验证跨模块接缝的实际行为；产出可直接转录进 code-review 报告 / CORRECTIONS-LOG 的走查记录
- 不做: 修改代码（仅报告，修复走标准 dev 流程）；替代 code-review 的任务粒度审查（互补：本 skill 以功能条目为单位、含符合性维度）；替代 sprint-review 的完成度审查（那是任务/AC 账面核对，本 skill 验运行态行为）；框架元资产走查（framework-walkthrough 负责）

## 两层正交判定

每个功能条目回答两个独立问题：

| 层 | 问题 | 判定值 |
|----|------|--------|
| 第一层·符合性 | 功能兑现 spec 了吗 | `missing`（缺失）/ `drift`（偏离）/ `bug`（错误）/ `pass`（通过） |
| 第二层·健康度 | 代码本身健不健康 | COMMON-RULES §统一问题分类体系 code category（structure / dead-code / duplication / complexity / coupling / test-quality / consistency …）+ severity + root_cause |

第二层与 code-review 共用 category / severity / root_cause 口径，走查发现可无缝进 code-review 报告与 CORRECTIONS-LOG 流程。

## 输入规范

- 必选：走查目标 —— 功能域名称 / 页面 / spec 条目引用（如 `prd#§2.F-003`）；`all` 表示全功能清单
- 可选 `--scope <dir>`: 限定代码扫描目录，缺省从 spec 条目的 traceability 推断
- 可选 `--round <N>`: 走查轮次，缺省自动递增（当日同 scope 已有 r1 则 r2）
- spec 事实源：经 `cataforge context read` 按条目粒度加载 prd / arch / ui-spec / dev-plan 相关章节，不整篇加载
- 第二层机检入口：`cataforge skill run code-review -- scan <scope> [--focus <category,...>]`

## 执行步骤（五步走查法，每个功能条目）

1. **读意图** — 加载该条目的 spec 原文（功能描述 + AC + 关联 UI/接口契约）
2. **对设计** — 找到承接该条目的模块/组件/入口，核对架构映射（traceability 边或代码引用）
3. **查实现** — 沿调用链读实现，标记与 spec 的差异候选
4. **跑符合性** — 用真实数据路径起真实服务，实际操作/调用该功能，判定 `missing|drift|bug|pass`
5. **扫质量** — 对该条目触达的代码区块跑第二层健康度（机检 probe + 人工核验），按统一分类体系记录

前四步查符合性，第五步扫质量；两层结论互不覆盖。

## 真实数据动态复现（硬纪律）

- 符合性判定**必须**以真实数据路径起真实服务的观察为准——桩数据/替身测试系统性漏「页面↔聚合器」等跨模块接缝，替身还可能引用已废弃的取值使断言失真
- 绿色单测/门禁不构成 `pass` 证据；`pass` 需引用运行态观察（实际输出、界面渲染、接口响应）
- 无法启动真实服务时如实记 `blocked` 并写明障碍，不降级为看代码推断

## 编排（可选加速）

- 按正交区块（功能域 / 页面 / 端到端流 / 边界条件）派发并行子代理分区走查
- 主线程对子代理上报的 HIGH 级发现**独立复核**（重跑其复现路径），防误判与门禁套利
- 单轮建议 ≤ 一个功能域，超出拆多轮

## 输出规范

- 走查报告: `docs/reviews/walkthrough/WALKTHROUGH-{scope}-{YYYYMMDD}-r{N}.md`，front matter `id: walkthrough-{scope}-{YYYYMMDD}-r{N}`、`doc_type: walkthrough`、`status: draft|approved`（字段按 COMMON-RULES §报告 Front Matter 约定）
- 走查记录一行一条，字段与 COMMON-RULES §问题格式 对齐：编号（W-NN）/ 位置 / 符合性判定 / 质量 category / severity / root_cause / 现象 / 证据（运行态观察引用）
- 发现的修复走标准 dev 流程；HIGH 及以上同步记 CORRECTIONS-LOG

## Anti-Patterns

- **拿绿门禁当符合性证据**：单测/lint/门禁全绿只说明账面合规，符合性判定必须来自第 4 步的运行态观察
- **只看替身不起服务**：以桩数据或替身测试的通过推断功能可用——跨模块接缝正是替身测不到的地方
- **两层判定互相污染**：把「代码脏但功能对」记成 `drift`，或把「代码干净但功能错」漏记——符合性与健康度各记各的
- **走查报告写进 docs/reviews/code/**：会污染 sprint-review 对代码审查报告的聚合；走查报告只落 `docs/reviews/walkthrough/`
- **发现即顺手修**：走查是验收活动，边走查边改码会破坏证据链；先出报告，修复另开任务
