# 审计：SDLC 人工审查检查点与可视化交付物呈现

> 状态：已实施。C1–C3 以单一 PR 合并落地（原 §5 三 PR 计划合并执行，依赖序不变），
> 以代码为准；本文余下为核实报告与决策记录存档。
> 范围：三项待核实问题——① prd/arch/ui-design 冻结后人工审查检查点缺口；
> ② 可视化能力未接入交付物呈现；③ 系统架构图 / 模块依赖图呈现缺失。
> 方法：主线程直读源码 / 配置 / 历史提案逐项证伪，承重结论均附 `file:line` 锚点；
> 未采信任何未经核验的转述。
> 交付边界：核实报告（§1–§3）、改进方案与决策记录（§4）、实施计划（§5）为本文职责；
> 实施代码以后续 PR 为准。

---

## 0. 三态结论一览

| # | 待核实问题 | 结论 |
| --- | ----------- | ------ |
| 1 | prd/arch/ui-design 冻结后缺人工检查点 | **部分缺陷（现有机制+缺口）** |
| 2 | 可视化未接入交付物呈现 | **部分缺陷（现有机制+缺口）** |
| 3 | 架构/模块图呈现缺失 | **部分缺陷（现有机制+缺口）** |

一句话结论：

- 问题 1：检查点机制完整、且已有专为「冻结前介入」设计的 `post_doc_freeze` 档位，
  但该档位定义漏掉 ui-spec 冻结（Phase 3→4）；要门禁 ui_design 收口只能升到最重的
  `phase_transition`。
- 问题 2：viz 已焊入 Bootstrap / dev-plan / Sprint 收口三处，且接入面收敛是有记录的
  设计决策（黑名单+重评条件）；缺口在文档冻结类检查点的阶段摘要为纯文本、零 viz 焊点，
  形成「开发侧有保底可视化、设计侧没有」的不对称。
- 问题 3：模块依赖图 `cataforge viz arch` 已可产出（CLI+SKILL 均在）；缺口在组合层级
  `part_of` 边未渲染（提案 §A 承诺、实现未兑现）与循环依赖无标注（tasks 视图有
  CYCLE/关键路径标注，arch 视图没有）。

三项均非「确为缺陷」——机制主体都在；也均非「非缺陷」——各有一处可坐实的窄缺口。

---

## 1. 问题 1 核实：人工审查检查点

### 1.1 现状事实：机制已存在且完整

- 检查点常量默认值 `[pre_dev, post_sprint, pre_deploy]`，单一事实源
  —— `.cataforge/rules/COMMON-RULES.md:27`；`framework.json#constants` 双写同值。
- 可选值表含升档档位：`phase_transition`（每次转换都停，隐含全部）与
  `post_doc_freeze`（冻结类文档转换后停）—— `COMMON-RULES.md:60-69`（:63 / :64）。
- 默认档不在 PRD/ARCH 冻结点单设确认是**有明确 rationale 的设计决策**：
  `pre_dev` 已在最贵阶段前 consolidate 全部上游冻结文档审查；需要早期冻结门禁的项目
  显式加 `post_doc_freeze` —— `COMMON-RULES.md:71`。
- orchestrator 侧执行协议完整：触发时机（文档 approved 且即将进入下一 Phase）、
  读项目覆盖值、命中即 AskUserQuestion 暂停 —— `ORCHESTRATOR-PROTOCOLS.md:220-246`。
- Bootstrap Step 1 向用户收集「人工审查检查点偏好」并指向可选值表
  —— `ORCHESTRATOR-PROTOCOLS.md:11`。
- 用户在文档产出**过程中**并非无介入：requirements / architecture / ui_design 三阶段均
  `execution_host: inline` + `interactive: true`（v0.9.1 design-phase-interactivity 落地），
  req-analysis 强制至少一轮 user-interview，architect 禁止零用户确认
  —— `framework.json:141-163`；`docs/proposals/design-phase-interactivity/analysis.md:2`；
  `req-analysis/SKILL.md:34`；`architect/AGENT.md:39`。
- doc-review 结论为 `approved_with_notes` 时用户另有「接受/修复/暂停」三选项介入点
  —— `ORCHESTRATOR-PROTOCOLS.md:115-129`。

### 1.2 现状事实：可坐实的缺口

`post_doc_freeze` 的触发时机定义为「PRD 冻结后（Phase 1→2）、ARCH 冻结后（Phase 2→3）」
（`COMMON-RULES.md:64`），**不含 ui-spec 冻结（Phase 3→4）**。而 standard 模式阶段序列中
ui_design 同样产出冻结类业务文档 ui-spec（`framework.json:156-162`）。后果：一个显式配置了
`post_doc_freeze`（说明其明确要求「冻结前介入」）且启用 UI 设计的项目，恰恰在视觉/交互
返工成本最高的 ui-spec 冻结点没有检查点；唯一替代是升到 `phase_transition`，代价是
**每次**阶段转换都暂停。档位粒度在中间档出现语义洞——该档位的自我描述是
「只门禁冻结类文档转换」，枚举却少列了一个冻结类文档。

「用户无法在冻结前介入」的**感知**另有一半来自默认档设计（干净 approved 直接推进），
这部分有 `COMMON-RULES.md:71` 的记录 rationale、有 Bootstrap 暴露通道（:11）与运行中
覆盖通道（项目指令文件 §全局约定），属「机制已存在但未被感知」，不动。

### 1.3 结论

**部分缺陷**：机制体系完整（常量 + 可选值表 + 协议 + Bootstrap 暴露 + 设计阶段本身交互式），
唯一实缺口是 `post_doc_freeze` 枚举漏 ui-spec 冻结点。修复见 §4.1（C1）。

---

## 2. 问题 2 核实：可视化接入交付物呈现

### 2.1 现状事实：已有焊点（并非「未接入」）

- Bootstrap Step 9：可选提示 `cataforge viz framework` 渲染编排图
  —— `ORCHESTRATOR-PROTOCOLS.md:40`。
- dev-plan 交付物内嵌图：task-decomp Step 6 用 `cataforge viz tasks --format mermaid`
  产依赖图写入 dev-plan#§2（并有反模式禁止手写 mermaid）
  —— `task-decomp/SKILL.md:42`；`project-visualization/SKILL.md:43`；`tech-lead/AGENT.md:71`。
- Sprint 收口可视化保底焊点：Sprint approved 后与进入 Phase 6 前，
  `cataforge viz dashboard -o docs/viz/dashboard.html` 并向用户提示产物路径；
  确定性 CLI、空数据跳过不阻塞 —— `ORCHESTRATOR-PROTOCOLS.md:346`。
- orchestrator 挂载 project-visualization skill，12 视图按情境自主选用
  —— `orchestrator/AGENT.md:14`；`project-visualization/SKILL.md:20-35`。

### 2.2 现状事实：接入面收敛是有记录的设计决策

`docs/proposals/visualization-integration.md`（状态：已实施，:3）§I 决策 2（:305）刻意把
提示词接入面收敛为「薄发现型 SKILL + orchestrator Sprint 收口焊点」，并列出
**不该碰黑名单**（:209）：`arc-design/SKILL.md`（理由「文档内嵌 Mermaid，非 viz 命令面」）、
`architect/AGENT.md`、`reviewer/AGENT.md` 等。留有重评条件：「若 SKILL 描述触发率仍低，
再在确有价值的单个 agent 定向加引用」。因此「未向各 agent 铺 viz 引用」本身不是缺陷，
是防腐决策。

### 2.3 现状事实：可坐实的缺口

Manual Review Checkpoint 的阶段摘要模板是纯文本（`ORCHESTRATOR-PROTOCOLS.md:232-240`：
「已完成/即将进入/三选项」），命中检查点时**没有任何 viz 产物伴随**——而这恰是用户
审查交付物、决定放行的时刻，也恰是 viz 已有视图（`viz arch` / `viz trace` / `viz tasks` /
`viz phase` / `viz dashboard`）的目标场景。对照 Sprint 收口焊点：开发收口有确定性保底
可视化，文档冻结收口没有。检查点协议属 orchestrator 协议，**不在**决策 2 黑名单内，
且「orchestrator 确定性焊点」正是决策 2 已确立的合法接入形态——缺口是该形态没有覆盖到
检查点这一环。

### 2.4 结论

**部分缺陷**：viz 已接入交付物链路三处且收敛有据；缺口收窄为
「检查点摘要环节零 viz 焊点」。修复见 §4.2（C2）。

---

## 3. 问题 3 核实：架构/模块图呈现

### 3.1 现状事实：模块依赖图已可产出

- CLI `cataforge viz arch` 在，SKILL 视图表列「架构模块依赖图」
  —— `src/cataforge/interface/cli/viz_cmd.py:182-186`；`project-visualization/SKILL.md:29`。
- collector 渲染 KG 中 Module/Component/API/DataModel 实体 + `depends_on` 边，
  mermaid/dot/json + `--html`（Cytoscape.js）全格式可出 —— `collectors/trace.py:28,137-152`。
- 数据源已闭环：arc-design Step 2 产 M-NNN（含依赖模块），经 context authoring 落图
  finalize，KG 即含 arch 层实体 —— `arc-design/SKILL.md:46-55,91`。
- 系统上下文图（C4Context）与 ER 图由 arch 文档 §1.3/§4.1 手写 mermaid 承载——
  外部系统/用户角色不入 KG，viz 无数据可渲，属文档创作内容而非 viz 缺口
  —— `templates/standard/arch.md:26-35,81-84`；`visualization-integration.md:209`（黑名单理由）。

### 3.2 现状事实：可坐实的缺口

1. **`part_of` 组合层级边未渲染**：提案 §A 数据源盘点承诺 arch 视图含
   「part_of/depends_on」两类边（`visualization-integration.md:33`），KG schema 中
   Component 也确有 `part_of` slot（`domain/kg/schemas/core.yaml:566-586,189-196`），
   但 `collect_arch` 只查 `depends_on`（`trace.py:149`；`domain/kg/query.py:332-346`
   只有 `cf:depends_on` 谓词）。后果：图中 Component 与其所属 Module 之间无边，
   「系统架构图」的层级结构缺失，只剩平面依赖图。
2. **循环依赖无标注**：arc-design 反模式硬性要求模块依赖为 DAG
   （`arc-design/SKILL.md:55,96`），tasks 视图已有环检测+关键路径标注
   （`collectors/tasks.py:69-77`，`Status.CYCLE` 在 `core/viz/model.py:30`），
   但 `collect_arch` 不做环检测——viz arch 面对违规架构时渲染不出任何警示，
   浪费了现成的 `detect_cycles`（`runtime.skill.builtins.task_dep_analysis`，
   application→runtime 为合法向下依赖）。

渲染器无 mermaid subgraph / dot cluster 分组能力（`core/viz/render/mermaid.py:45-57`
平面发射；`Graph` IR 无分组槽，`core/viz/model.py:55-65`）——这是实现「分层架构图」的
更重路径，本次不动（见 §4.3 取舍）。

### 3.3 结论

**部分缺陷**：「模块依赖图」已覆盖（非缺陷成分）；「系统架构图」的组合层级边与环标注
是实缺口（提案承诺未兑现 + 既有能力未复用）。修复见 §4.3（C3）。

---

## 4. 改进方案

三项改进各自独立、均复用现有机制，不新增任何数据层 / 命令面 / 档位体系。

### 4.1 C1 · `post_doc_freeze` 语义补全（问题 1）

**改动**：`COMMON-RULES.md:64` 一行——触发时机改为「冻结类业务文档 approved 后的阶段转换：
PRD（Phase 1→2）、ARCH（Phase 2→3）、UI-SPEC（Phase 3→4；ui_design 标 N/A 时该点自然
不存在）」。协议零改动（`ORCHESTRATOR-PROTOCOLS.md:227` 按值表判断命中，值表是唯一
语义源）；默认值不变，`framework.json` 常量双写不变。

**决策记录**：

- 选项 A（取此）：扩 `post_doc_freeze` 语义——该档位自述「只门禁冻结类文档转换」，
  ui-spec 就是冻结类文档，这是**语义修复**而非新特性；一行改动，档位数不变。
- 选项 B：新增 `post_ui_freeze` 档位——档位增殖，三个冻结点三个档位没有配置学意义，
  用户组合负担上升；且与 A 相比不解决「B 档用户漏配」问题。
- 选项 C：不动，靠 `phase_transition`——把「想在 3 个冻结点停」的用户强推到
  「7 个转换点都停」，粒度惩罚过重。

重评条件：若下游反馈 ui-spec 冻结暂停在多数 UI 项目中被机械式放行（无实际审查行为），
降回原枚举并在值表注明 ui-spec 由 `pre_dev` consolidate。

**影响边界**：下游已配 `post_doc_freeze` 且启用 ui_design 的项目升级后多一次暂停
（行为变化，changelog 声明）；默认档项目零影响；元项目不跑 SDLC 管线，零影响。

**明确不做**：不动默认值（`COMMON-RULES.md:71` rationale 成立）；不强化 Bootstrap 暴露
（`ORCHESTRATOR-PROTOCOLS.md:11` 已指向可选值表，COMMON-RULES §全局约定「选择题优先」
已约束提问形态；为凑感知度在 Bootstrap 加档位科普违反硬约束 1）。

### 4.2 C2 · 检查点摘要可视化附件焊点（问题 2）

**改动**：`ORCHESTRATOR-PROTOCOLS.md` §Manual Review Checkpoint Protocol Step 3 内加一句：
命中检查点时，展示摘要前按转换类型运行匹配视图并在摘要附产物路径——冻结类文档检查点
（`post_doc_freeze`）→ `cataforge viz arch --format mermaid`（ARCH/UI-SPEC 冻结）或
`viz trace`（PRD 冻结）；`pre_dev` → `viz tasks`；`post_sprint`/`pre_deploy` → 复用既有
Sprint 收口 dashboard 产物路径。语义与 Sprint 收口焊点完全一致：确定性 CLI、不阻塞推进、
数据源未就绪跳过不报错。

**决策记录**：

- 选项 A（取此）：检查点协议焊点——复用决策 2 已确立的「orchestrator 确定性焊点」形态
  与 Sprint 收口的成熟语义；一处改动覆盖所有检查点档位；图给「人」看，焊在人介入的环节。
- 选项 B：arc-design 产图嵌入 ARCH 文档（对称 dev-plan 嵌图）——触碰决策 2 黑名单需
  行使重评条件；且 ARCH 模块依赖已有 KG+文本列表双承载，下游 agent 经 context read
  结构化消费不需要嵌图，嵌图只服务人的审查——A 已覆盖该场景且不增加文档再生成负担。
- 选项 C：doc-review 加 viz——违反 viz 能力边界「不出审查 verdict」
  （`project-visualization/SKILL.md:17,45`），且 reviewer 在黑名单。

本决策同时构成对 visualization-integration §I 决策 2 重评条件的一次行使记录：
不向 agent 主体散加引用的原则不变，仅扩展「orchestrator 焊点」清单
（Sprint 收口 → Sprint 收口 + 检查点）。

**影响边界**：仅下游业务项目 SDLC 运行时行为；元项目零影响。提示词改动量最小，
满足硬约束 1/2/3（无语言耦合、无残留、编号连续）。

### 4.3 C3 · `collect_arch` 补 `part_of` 边与环标注（问题 3）

**改动**（`src/cataforge/application/viz/collectors/trace.py` + `domain/kg/query.py`）：

1. `QueryAPI` 增 `part_of` 查询（镜像 `depends_on()`，谓词换 `cf:part_of`；
   `query.py:332-346` 模式复制）。
2. `collect_arch` 追加 `part_of` 边（label=`part_of`，与 `depends_on` 区分）——
   组合层级以带标签边表达。
3. `collect_arch` 对 `depends_on` 子图跑既有 `detect_cycles`，环上节点标 `Status.CYCLE`
   （复用 `tasks.py:69-77` 模式；application→runtime 合法向下依赖）——viz arch 从此
   直接暴露违反 arc-design DAG 反模式的架构。

**决策记录**：

- 选项 A（取此）：带标签边 + 环标注——零 IR/渲染器改动，兑现提案 §A 原承诺，
  复用既有 Status 语义与检测算法；mermaid/dot/json/html 四格式自动受益。
- 选项 B：渲染器扩 mermaid subgraph / dot cluster 分组——需动 `Graph` IR（加分组槽）+
  三个文本渲染器 + HTML 渲染器，波及所有既有视图的回归面；层级信息用带标签边已可表达，
  分组是纯视觉增强。

重评条件：若下游反馈大型项目（模块数 >30）下带标签边的层级可读性不足，再评估 B
（届时 IR 加可选 `group` 槽，沿用 `Node.data` 的「文本渲染器忽略、富渲染器消费」先例）。

**影响边界**：`cataforge` 包代码，随版本发布到下游；`viz arch --format mermaid` 文本输出
新增边与状态标记（增量，不破坏既有消费方——json 契约只增不改）；元项目自身 KG 无业务
arch 实体，`viz status` 自陈空视图，无影响。

---

## 5. 实施计划

三个步骤单元（原计划各自一个 PR，实际以单一 PR 合并落地，依赖序与验收判据不变）：

- **PR-1 · `fix(rules): post_doc_freeze covers ui-spec freeze`**（P0，无依赖，与 PR-2 并行）
  内容：C1——`COMMON-RULES.md:64` 一行 + `changelog.d`（标行为变化）。
  验收：值表含 Phase 3→4；`run_local.py` 绿。
- **PR-2 · `feat(viz): arch view part_of edges + cycle marking`**（P1，无依赖，与 PR-1 并行）
  内容：C3——QueryAPI `part_of` + collect_arch 两类边 + 环标注 + 测试
  （含 mermaid 回归断言、环样本断言）+ `changelog.d`。
  验收：环样本图节点带 CYCLE 标记；part_of 边带 label；json 契约向后兼容断言；
  `run_local.py` 绿。
- **PR-3 · `feat(skill): manual checkpoint viz attachment`**（P1，置后收尾）
  内容：C2——Manual Review Checkpoint Protocol 焊点 + 本提案 §4.2 决策记录即重评记录 +
  `changelog.d`。
  依赖：软依赖 PR-2（焊点引用的 `viz arch` 已存在可独立合入，但 ARCH 冻结场景在 PR-2 后
  才含层级与环标注，建议置后——同 visualization-integration「PR-G 依赖其引用的 view
  已存在」教训）。
  验收：提示词守卫（design-residue / language-coupling / doc-structure /
  prompt-cli-drift）绿；`run_local.py` 绿。

依赖链：**PR-1 ∥ PR-2 → PR-3**。每步自带测试与 changelog 片段义务
（`check_changelog_fragments.py`）。

**明确不做**（防止凑改进量）：不动检查点默认值；不强化 Bootstrap 档位科普；
不给 arc-design/arch 模板嵌图；不扩渲染器分组；不给 doc-review 加 viz；
不新增检查点档位。
