# 设计阶段交互能力修复 — 详细方案与实施计划

> 前序：本目录 [`analysis.md`](analysis.md)（问题核实与证据链）。本文是基于用户决策拍板后的**详细方案 + 分步实施计划**。
> 交付边界：本轮**仅出方案与计划**，不改动 agent / skill / 协议本体（待用户审阅后另行立项实施）。

---

## 0. 决策基线（已拍板）

| 决策项 | 结论 | 对方案的影响 |
|--------|------|------------|
| **方案范围** | **方案 A — PRD/ARCH 全程主线程内联** | Phase 1/2 不再派子代理，由 orchestrator 主线程内联承载 PM/architect 角色执行；交互工具原生可用 |
| **澄清蓝本形态** | **轻量工作文件** | 不新增正式 doc_type；复用既有 `docs/research/` research-note + PRD/ARCH 文档内「决策记录」段承载澄清/调研痕迹 |
| **问题①（协议骨架数据化）** | **纳入本轮一并规划** | 与方案 A 的「执行宿主」维度合流为同一张结构化 workflow 表 |
| **交付节奏** | **仅出详细方案与计划** | 本文即交付物；不落地改动 |

---

## 1. 方案 A 架构设计

### 1.1 核心变更

Phase 1（requirements）与 Phase 2（architecture）的**执行宿主**从「派发子代理」改为「主线程内联承载角色」：

```
变更前：orchestrator --agent-dispatch--> [product-manager 子代理(隔离/非交互)] --> prd
变更后：orchestrator --主线程内联加载 product-manager 角色 + req-analysis/research skill--> prd
        （AskUserQuestion / research user-interview / 多轮头脑风暴 在主线程原生可用）
```

「内联承载角色」= orchestrator 主线程 Read 该 phase agent 的 AGENT.md（角色定义/约束/skills）+ 执行其核心 skill，**在主线程上下文中扮演该角色**。角色定义、Anti-Patterns、skill 工具链全部复用，**仅执行宿主从子代理改为主线程**。

### 1.2 架构先例：这不是新机制

Phase 5（development）**已经**是这种形态——`orchestrator/AGENT.md:60`「开发阶段由 orchestrator 通过 tdd-engine skill 直接编排」，orchestrator 主线程内联跑 tdd-engine，而非派一个「dev-agent 子代理」。`framework.json#/dispatcher_skills` 已把 `tdd-engine` / `start-orchestrator` 登记为 skill-as-router（B5-α 豁免 agent 存在性检查）。

方案 A 把同一模式扩展到 Phase 1/2：**发散性阶段由主线程内联承载，收敛性阶段派子代理**。判据是**任务是否需要与用户实时往返**，而非阶段编号。

### 1.3 哪些环节仍派子代理（隔离收益保留处）

| 环节 | 宿主 | 理由 |
|------|------|------|
| Phase 1/2 内容生产（PM/architect） | **inline** | 发散、需多轮交互澄清 |
| Phase 1/2 **审查门禁（reviewer）** | **subagent（不变）** | 收敛任务，输入已是定稿文档，不需交互；隔离审查独立性有价值 |
| Phase 3 ui_design / Phase 4 dev_planning / Phase 6/7 | subagent（本轮不变） | 见 §1.4 |
| Phase 5 development | inline（经 tdd-engine，现状） | 已是先例 |

> 即「内联」只针对发散性的**内容生产**段；**审查门禁仍走子代理**，隔离收益在最该独立的环节保留。

### 1.4 一致性观察（不在本轮强制改，仅标注）

`ui-design/SKILL.md` 同样含 user-interview 步骤（信息密集 vs 内容聚焦的取向需与用户确认），Phase 3 ui_design 有与 Phase 1/2 **同构的交互需求**。本轮按用户决策聚焦 Phase 1/2；但 §5 的结构化 workflow 表会把「执行宿主」做成一等数据，使 Phase 3 将来切 inline 只是改一个字段 + 守卫放行，无需再动协议本体。

---

## 2. 需正面处理的张力与缓解

方案 A 与现有设计有真实冲突，必须在实施中显式处理，否则引入新缺陷。

| # | 张力 | 缓解措施 |
|---|------|---------|
| T1 | **与 orchestrator「不直接产业务文档」原则冲突**（`orchestrator/AGENT.md:21,77`） | 改写该原则：区分「越权替代 agent 做内容决策」（仍禁止）与「主线程内联承载 phase agent 角色执行」（新增允许，与 DEV 阶段内联编排 tdd-engine 同构）。Anti-Pattern 由「不在主线程撰写 PRD 而应派发 product-manager」改为「内联承载 product-manager 角色时须完整加载其 AGENT.md 约束，不得跳过角色定义直接以 orchestrator 身份决策」 |
| T2 | **主线程上下文污染**（PRD/ARCH 重型文档全程在主线程） | ① 内容经 `context finalize` 落盘后，主线程仅保留 `doc_id` 引用 + ≤3 句摘要，不滞留全文（context 已支持按引用加载）；② **审查门禁派子代理**，重型审查上下文不进主线程；③ 一个 inline phase 完成后其工作上下文不被下游 phase 需要，自然释放 |
| T3 | **写入边界保护丢失**：子代理 PM 有 `allowed_paths: docs/prd/` + agent-dispatch §写入范围校验回滚；主线程 `allowed_paths: []` 无限制 | 新增**内联角色写入自检**：内联承载某角色执行后，orchestrator 以该角色 AGENT.md 的 `allowed_paths` 为基准跑一次 `git diff --name-only` 校验，越界文件回滚（复用 agent-dispatch §写入范围校验 Step 5 逻辑，宿主从子代理返回改为内联段结束） |
| T4 | **平台一致性** | 方案 A 平台无关（主线程在 claude-code/cursor/codex/opencode 均可交互），统一改 inline，**不引入 per-platform 分支**（用户未选方案 D）。其他平台同样放弃 Phase 1/2 子代理隔离——可接受，交互正确性优先于隔离 |
| T5 | **needs_input 路径的去留** | 内联执行后，user-interview 在主线程直接做，**不再需要** Phase 1/2 的 needs_input→continuation 回路。但保留该回路给仍是子代理的 Phase 3/4/6/7。同时清理 §1.3 的错误前提（见 §4 Step 1） |

---

## 3. 轻量工作文件设计（澄清/调研痕迹）

按「轻量工作文件」决策，**不新增 doc_type / 模板 / doc-index 注册**，复用既有机制承载澄清痕迹：

- **调研痕迹** → 既有 `docs/research/` research-note（`research/SKILL.md` 指令 1 已产出，含来源 URL + 可信度）。
- **澄清结论 / 选型决策** → 写入 PRD / ARCH 文档内既有「决策记录」段（呼应 COMMON-RULES §决策记录要求：考虑了哪些选项 / 为何选当前 / 何时重评）。
- **多轮交互过程**本身**不落正式文件**——主线程对话上下文即过程，结论沉淀到上述两处即可追溯。

收益：零 schema 改动、不增 doctor orphan 面、不污染 doc-index；与「轻量」一致。

---

## 4. 问题① 骨架数据化设计（与方案 A 合流）

把「Phase Routing 散文表」提升为 `framework.json` 结构化单一事实源，**执行宿主作为一等字段**——这正是方案 A 需要落的数据。

### 4.1 framework.json 新增 `workflow` 段（草案 schema）

```jsonc
"workflow": {
  "modes": {
    "standard": {
      "phases": [
        { "phase": "requirements",  "role": "product-manager", "skills": ["req-analysis","research"], "output_doc_type": "prd",       "execution_host": "inline",   "interactive": true,  "guard": "requirements" },
        { "phase": "architecture",  "role": "architect",       "skills": ["arc-design","tech-eval"],   "output_doc_type": "arch",      "execution_host": "inline",   "interactive": true,  "guard": "architecture" },
        { "phase": "ui_design",     "role": "ui-designer",     "skills": ["ui-design"],                "output_doc_type": "ui-spec",   "execution_host": "subagent", "interactive": true,  "guard": "ui_design", "skippable": true },
        { "phase": "dev_planning",  "role": "tech-lead",       "skills": ["task-decomp"],              "output_doc_type": "dev-plan",  "execution_host": "subagent", "interactive": false, "guard": "dev_planning" },
        { "phase": "development",   "role": "tdd-engine",      "skills": ["tdd-engine"],               "output_doc_type": "code",      "execution_host": "inline",   "interactive": false, "guard": "development" },
        { "phase": "testing",       "role": "qa-engineer",     "skills": ["testing"],                  "output_doc_type": "test-report","execution_host": "subagent","interactive": false, "guard": "testing", "skippable": true },
        { "phase": "deployment",    "role": "devops",          "skills": ["deploy-config"],            "output_doc_type": "deploy-spec","execution_host": "subagent","interactive": false, "guard": "deployment","skippable": true }
      ]
    },
    "agile-lite":      { "phases": [ /* planning(inline) → dev_planning → … */ ] },
    "agile-prototype": { "phases": [ /* brief(inline) → development(inline) */ ] }
  }
}
```

要点：
- `execution_host: inline|subagent` 是方案 A 的承载字段；Phase 1/2 = inline。
- `interactive: true` 标交互密集 phase，供新增守卫校验「interactive ⇒ host 必须能交互」。
- `guard` 复用现有 `features[*].phase_guard` 的 phase 命名（B5-δ 已对账），保持一致。

### 4.2 markdown 协议降为「视图」

`orchestrator/AGENT.md` 的 Phase Routing 列表与 `ORCHESTRATOR-PROTOCOLS.md` 的路由表**保留为人类可读视图**，但顶部标注「**权威源见 `framework.json#/workflow`，本表为只读视图**」——复用 `agent-dispatch/SKILL.md:32` 已有的「单一事实来源…本文件不维护映射副本」模式。

### 4.3 framework-review B5 改造 + 新增守卫

| 检查项 | 变更 |
|--------|------|
| B5-α / B5-β | 数据源从「正则解析 orchestrator markdown 路由表」改为「读 `framework.json#/workflow`」，矩阵生成更稳（消除散文正则脆弱性） |
| **B5-ζ（新增）** | `interactive: true` 的 phase 其 `execution_host` 必须为 `inline`（或平台 profile 声明子代理可交互）——把本次缺陷固化为守卫，防回归。**FAIL** 级 |
| B5-δ | `features[*].phase_guard` ↔ `workflow` phase 名对账（已有逻辑，数据源对齐后更直接） |

---

## 5. 详细实施计划（分步、仅规划）

> 每步独立可提交。复杂度用「成本/影响面」描述（不估时）。验收 = framework-review + run_local.py 全绿且行为符合预期。

### Step 1 · 纠正错误前提（文档事实，最小、先行）
- **改动**：`ORCHESTRATOR-PROTOCOLS.md:112`、`research/SKILL.md:36` 删除「前台子代理可直接用 AskUserQuestion」错误表述，改为「主线程可直接交互；派发子代理为非交互执行体」。全仓 grep `前台子代理|后台子代理` 统一口径为「主线程 vs 派发子代理」。
- **影响面**：纯文档，2 文件。**前置**：必须先于 Step 2，避免新协议建立在错误前提上。
- **验收**：grep 无残留旧口径；framework-review B1/B4 无新 WARN。

### Step 2 · framework.json 落 `workflow` 段（数据先行）
- **改动**：新增 `framework.json#/workflow`（§4.1 schema），三模式 phases 全列，Phase 1/2 标 `execution_host: inline` + `interactive: true`。
- **影响面**：单文件配置 + 需补 schema 校验（若 framework.json 有 schema 镜像，同步更新 `scripts/checks` 的 schema 镜像 parity 守卫）。
- **验收**：`run_local.py` schema parity 绿；`python -c "json.load"` 可解析。

### Step 3 · orchestrator 内联执行协议
- **改动**：
  - `orchestrator/AGENT.md`：Phase Routing 顶部标注「权威源 framework.json#/workflow」；改写 Identity/Anti-Pattern 解决 T1（区分越权 vs 内联承载角色）。
  - `ORCHESTRATOR-PROTOCOLS.md`：新增 **§Inline Role Execution Protocol**——orchestrator 对 `execution_host: inline` 的 phase，主线程 Read 该 role 的 AGENT.md + 执行其 skill，内联完成后跑 T3 写入自检；`execution_host: subagent` 的 phase 仍走 agent-dispatch（现状）。Phase Transition Protocol Step 6「激活下一阶段 Agent」改为「按 workflow.execution_host 分派 inline / subagent」。
- **影响面**：协议本体（中等），是方案核心。注意 META_DOC_SPLIT_THRESHOLD_LINES（500 行）——`ORCHESTRATOR-PROTOCOLS.md` 已 33KB，新增协议需控量或拆分。
- **验收**：framework-review B5 矩阵正确反映 inline/subagent；B1-β 行数未超阈值（超则拆分）。

### Step 4 · PM / architect 契约对齐内联宿主
- **改动**：`product-manager/AGENT.md`、`architect/AGENT.md`：Anti-Patterns 中「至少执行一轮 user-interview」「须经用户确认」在内联宿主下天然成立，措辞对齐为「在主线程内联执行时直接 user-interview 多轮澄清」；保留 needs_input 描述供其它（subagent）调用面。澄清结论落 §3 既有「决策记录」段。`req-analysis/SKILL.md` Step 1 标注内联/子代理两种入口。
- **影响面**：3 文件 agent/skill 主体。注意硬约束 1（最小可行修改，不留变更叙事）。
- **验收**：framework-review B8 Anti-Patterns 维度绿；check_no_design_residue 绿。

### Step 5 · framework-review B5 改造 + B5-ζ 新增守卫
- **改动**：`cataforge.runtime.skill.builtins.framework_review`——B5-α/β 数据源改读 `framework.json#/workflow`；新增 **B5-ζ**（interactive ⇒ inline）；`framework-review/SKILL.md` 的 Layer 1 检查项段同步加锚点（B3-α 对账）。补单测。
- **影响面**：runtime 代码 + 守卫单测 + SKILL.md（需走 TDD：RED 写 B5-ζ 失败用例 → GREEN）。本步是唯一含 `src/` 代码改动者，按本仓 TDD 门禁走。
- **验收**：新单测覆盖 B5-ζ 正/反例；CHECKS_MANIFEST ↔ SKILL.md 锚点对账绿。

### Step 6 · 端到端校验
- **改动**：无（验证步）。
- **动作**：`cataforge skill run framework-review -- all`（确认无新 FAIL）+ `uv run --extra dev python scripts/checks/run_local.py` + framework-review Layer 2 `--target product-manager/architect/orchestrator` 复核 Identity↔Phase、Anti-Patterns 具体性。
- **验收**：全绿；人工走查一次 Phase 1 内联问答闭环（主线程 AskUserQuestion 实际触达用户）。

### 步骤依赖图
```
Step1(文档纠正) ─┐
                 ├─> Step3(内联协议) ─> Step4(PM/arch契约) ─┐
Step2(workflow数据)┘         └────────> Step5(B5守卫/代码) ─┴─> Step6(E2E校验)
```
Step 1/2 可并行起步；Step 5 依赖 Step 2 的数据结构定型。

---

## 6. 风险与回滚

| 风险 | 级别 | 缓解 / 回滚 |
|------|------|------------|
| 主线程上下文在大型 PRD/ARCH 项目下膨胀 | MEDIUM | T2 缓解；若实测仍重，可对超大文档退回「主线程发散澄清 → 子代理收敛产文」的方案 C 混合形态（数据层 `execution_host` 已留扩展位，改字段即可，无需重写协议） |
| 内联失去 allowed_paths 硬隔离 | MEDIUM | T3 写入自检兜底；回滚为该 phase 改回 `execution_host: subagent` 一字段 |
| ORCHESTRATOR-PROTOCOLS.md 超行数阈值 | LOW | Step 3 控量或按 META_DOC_SPLIT 拆分 |
| 其它平台子代理交互语义与假设不符 | LOW | 方案 A 统一 inline 本就不依赖子代理交互，平台无关 |

**整体可回滚性强**：方案核心是 `execution_host` 一个数据字段 + 一段内联协议；任何 phase 出问题，改字段即退回子代理形态，不留架构债。

---

## 7. 范围边界（本轮不做）

- 不实施任何改动（仅计划，决策基线第 4 项）。
- 不引入方案 D 的 per-platform `subagent_interactive` 能力门控（用户选 A 非 D；workflow 表已为将来泛化留位）。
- 不改 Phase 3 ui_design 的宿主（仅 §1.4 标注同类候选，留待用户决策）。
- 不新增澄清蓝本 doc_type（决策为轻量工作文件，复用 research-note + 决策记录段）。
