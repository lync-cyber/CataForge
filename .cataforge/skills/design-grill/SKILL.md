---
name: design-grill
description: "可选的设计深度澄清策略 — 对 PRD、Architecture 或 UI 设计沿决策依赖树逐项收敛。仅在用户显式要求开启 Grill，或用户明确接受当前阶段的一次性建议后使用；普通信息缺口不触发。"
argument-hint: "<prd|arch|ui> [需要深度澄清的范围]"
suggested-tools: [file_read, file_glob, file_grep, web_search, web_fetch, user_question]
depends: [context, research, penpot-bridge]
disable-model-invocation: false
user-invocable: true
---

# 设计深度澄清 (design-grill)

## 启用门

本策略默认关闭。首条动作必须核实显式同意，仅在用户明确要求「开启 Grill」「深挖这个 PRD/架构/UI」「grill me」，或当前阶段发现高影响歧义、一次性建议后用户明确接受时运行。自动建议不等于启用；不得仅因「信息不完整」或「需要澄清」自动进入。未满足显式同意时立即返回原阶段，以 research user-interview 做普通澄清。

scope 取 `prd | arch | ui`，限当前阶段或用户指定范围；Grill 是阶段内策略，不改变 phase、执行模式或长期项目偏好。完成或退出后把总结交回 req-analysis、arc-design 或 ui-design，恢复原阶段流程。

## 能力边界

- 能做: 对 PRD、Architecture、UI 设计构建决策依赖树，核验本地事实，给出有依据的推荐，逐项收敛并输出阶段可消费的可追溯总结
- 不做: 代替阶段 Skill 产出完整 PRD、Arch 或 UI-SPEC，代替用户作最终业务或审美决定，或创建平行的长期决策事实源
- 不做: 把普通缺字段变成持续访谈；未启用时不改变正常阶段流程

## 输入规范

- scope 与需深度澄清的范围
- 当前会话已确认的用户意图与选择
- 当前执行模式、阶段状态，以及已有阶段文档、research-note、代码、配置和设计资产

## 输出规范

- 会话内工作台账: 决策依赖、事实来源、推荐、用户反馈、假设、未决项与受影响分支
- 每个阶段的一次连续 Grill 会话最多维护一份 research-note，作为过程证据；不按问题创建文件
- 完成、暂停或停止时输出共同理解总结，供当前阶段 authoring 写入终态权威文档

## 执行流程

### Step 1: 模式与上游边界

- `standard`: PRD、Arch、UI 可分别运行并保持独立台账；仅 Arch 可筛选 ADR 候选；UI 在 Design-Tool Capability Gate 通过后才可读取 Penpot
- `agile-lite`: 只收敛影响 lite 产物的高影响问题；planning 中先 `prd` 后 `arch`，UI 仅在显式启用 UI 阶段时运行；Arch-lite 不创建 ADR，UI-SPEC-lite 不扩张为完整页面、路由或响应式规格。核心决定无法在 lite 边界表达时建议切换 standard，不自动切换
- `agile-prototype`: 不自动建议 Grill；用户显式要求时只对 brief 中的产品、技术或 UI 意图做受限澄清。发现复杂架构、多页面、长期演进或高风险决策时建议升级模式，不自动创建完整阶段文档或 ADR
- 问题越过当前 scope 时停止该分支：产品功能、业务流程、权限或交互语义交回 PRD；API、数据、系统能力或实现边界交回 Arch

### Step 2: 建立本地事实包

按本地事实优先顺序查明问题，能确定的内容不得再询问用户：

1. 当前会话中用户已明确表达的事实和选择
2. 项目指令文件、framework 配置、当前执行模式和阶段状态
3. `cataforge context read` 返回的 PRD、Arch、UI-SPEC 与 research 内容
4. 现有代码、依赖清单、配置、API、数据结构、样式 Token 和设计资产
5. `design_tool=penpot` 且 Capability Gate 已通过时，经 penpot-bridge `read` 获取结构、样式、Token 实值；必要时 `export_shape` 做视觉 grounding
6. 已有 research-note
7. 必要的官方外部资料；技术版本与生命周期委托 tech-eval 核实
8. 仍无法核实的推断，显式标为 `[ASSUMPTION]`

事实冲突时列出冲突、来源与权威范围，只让用户裁决意图或权威归属。代码用于核实现状，不自动等同于用户意图。

### Step 3: 维护决策依赖树

维护当前 scope 的决策依赖树，只询问父决策已具备但尚未解决的前沿节点。父决策未确认时不询问依赖它的子决策；用户修改上游决定时，只重开受影响的下游分支。

按以下顺序选择问题：

1. 阻塞多个下游决定的父节点
2. 难以逆转或返工成本高的决定
3. 用户意图与本地事实的冲突
4. 安全、隐私、合规、数据正确性、可访问性等关键约束
5. 可逆但影响阶段产物结构的决定
6. 可安全采用默认值的局部细节

### Step 4: 问题契约

- 默认每轮一个高杠杆问题；仅相互独立或同属一个已确认父决策的问题可合并，每批不得超过 `MAX_QUESTIONS_PER_BATCH`
- 每个问题最多提供四个互斥选项，且必须包含待解决决策、受阻下游、推荐选项、推荐依据、主要代价或重评条件、用户快捷控制
- 推荐不得只依据流行度、所谓最佳实践或模型习惯；证据不足时，推荐可以是「暂缓决定并先补事实」

使用以下格式：

```text
决策：{需要确认的事项}
影响：{会解锁或改变的下游决定}

A. {选项}
B. {选项，推荐}
C. {选项}

推荐 B：{本地事实、上游文档或调研依据}
代价/重评条件：{主要代价；何时重新考虑}

可回复：接受建议 / A / C / 跳过 / 暂停 Grill / 停止并总结
```

### Step 5: 控制与恢复

- `接受建议`: 记录推荐项、依据和用户接受事实
- `接受本轮建议`: 仅在同批每个问题都有独立推荐时接受全部推荐
- `跳过`: 可逆项记为显式 `[ASSUMPTION]`；阻塞项保持未决并记录影响，不宣称完整收敛
- `暂停 Grill`: 保存当前检查点并更新单份 research-note，不推进正式阶段 authoring
- `停止并总结`: 输出已决、假设、未决及其影响，让用户选择按普通流程继续或保持暂停
- `继续 Grill`: 加载当前阶段最新 research-note 和阶段草稿，从首个未决依赖恢复，不重问已解决问题

一个依赖分支收敛、用户暂停或退出时更新 research-note；会话中不因每条回答频繁重写正式阶段文档。

### Step 6: 收敛与交回

Grill 不按固定轮数退出。仅当以下条件全部成立时视为完整收敛：

- 当前阶段所有高影响决定已确认、明确委托推荐默认或显式延期
- 决策依赖无矛盾，且本地事实、用户选择、推荐、推断和假设可区分
- 剩余问题均低风险、可逆或不属于当前阶段
- 已形成共同理解总结并由用户确认

继续追问只会增加低价值细节时，主动推荐退出 Grill。总结包含：

- 本次范围；已确认决策；用户接受或拒绝的关键推荐
- 已核实本地事实及来源；假设清单
- 未决问题、owner、影响和重评条件
- 术语变化；ADR 候选（仅 Arch）
- 应写入当前阶段产物的章节映射
- 下一步：继续 Grill、确认总结并恢复阶段流程、或暂停

阶段 Skill 将终态结论写入 PRD、Arch 或 UI-SPEC；research-note 是过程证据，阶段文档是终态权威。阶段文档 approved 后，后续变化走既有 amendment、revision 与 reconcile 流程，research-note 不反向覆盖 approved 文档。

## Scope profile 路由

scope 确认后按 scope 只加载一份对应 reference，不得预加载其他 profile：

- `prd` → [PRD Grill profile](references/prd.md)
- `arch` → [Architecture Grill profile](references/architecture.md)
- `ui` → [UI Grill profile](references/ui.md)

reference 定义该阶段的事实来源、决策树、推荐依据、上游边界和产物归属；通用启用门、问题契约、控制、收敛与生命周期仍以本文件为准。

## Anti-Patterns

- 禁止: 在用户未显式同意时自动运行，或把普通需求缺口升级为 Grill
- 禁止: 询问能从仓库、代码、配置、现有文档、research-note 或设计资产核实的事实
- 禁止: 在父决策未确认时机械展开子问题，或为增加完整感持续追问低价值细节
- 禁止: 让 research-note、Grill 总结、独立 decision log 或设计 glossary 成为平行权威源

## 效率策略

- 先核事实再提问，每轮优先解决能解锁最多下游决定的前沿节点
- 接受推荐作为快捷路径，但保留依据、代价和用户接受事实
- 分支收敛、暂停或退出时才更新 research-note，正式阶段文档在恢复阶段 authoring 后集中写入
