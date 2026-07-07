# 设计阶段（PRD / ARCH）交互能力缺口分析与改进方案

> 状态：已实施（v0.9.1「design-phase inline execution」）。配套 [`plan.md`](plan.md) 的方案 A 已落地——`framework.json#/workflow` 成为阶段路由骨架单一事实源（问题①：orchestrator markdown 路由表降为只读视图），Phase 1/2 改主线程内联承载角色（问题②：AskUserQuestion / user-interview 原生可用）。本文留作缺口分析与设计记录，以代码为准。
> 范围：orchestrator 调度协议（`ORCHESTRATOR-PROTOCOLS.md` / `ORCHESTRATOR-META-PROTOCOLS.md`）+ Phase 1/2 子代理（product-manager / architect）+ 相关 skill（research / req-analysis / agent-dispatch）+ claude-code 平台 profile。
> 方法：framework-review Layer 1 全量静态检查（`cataforge skill run framework-review -- all`，结果 PASS / 仅 1 无关 WARN）+ 调度链路逐文件证据核查 + 运行时交互语义核实。
> 触发问题：① 调度协议用 markdown 是否有更优格式？② PRD / ARCH 阶段以子代理执行，导致 research / req-analysis / AskUserQuestion 的「广泛调研 + 头脑风暴 + 向用户澄清」无法正常工作。

---

## 0. 总体判断

两个问题中，**问题 ② 是真实且可核实的设计缺陷**，问题 ① 不是缺陷而是一个可优化点。

- **问题 ②（已核实，CRITICAL）**：框架在文档层面**断言**「前台子代理可直接使用 AskUserQuestion」，但这把**同步调度（synchronous）**与**可交互（interactive）**两个概念混为一谈。在 Claude Code 运行时，经 `Agent` 工具以 `subagent_type` 派发的子代理是**非交互**执行体——其最终消息作为工具结果回传给调用方、**不呈现给用户**，子代理内部调用 AskUserQuestion 无法形成真正的「向人提问—等人回答」回路。因此 PM / architect 作为子代理运行时，user-interview / 头脑风暴 / 多轮澄清在 Claude Code 上**无法按设计工作**；而 PRD / ARCH 恰恰是全流程中**最依赖与用户往返澄清**的两个发散性阶段。用户的观察成立。

- **问题 ①（非缺陷）**：markdown 是 LLM 消费型协议的**正确**载体（指令遵循度最高）。真正的脆弱点不在「markdown vs 其他格式」，而在于**确定性的状态机骨架（阶段路由表、状态转移、守卫条件）被埋在散文里、靠正则解析**（framework-review B5-α 即正则解析 Phase Routing markdown 表）。优化方向是把这层确定性骨架抽成机器可校验的单一事实源，而非替换 markdown。

---

## 1. 问题 ② 核实：证据链

### 1.1 设计意图：PM / architect 本应交互式澄清

| 证据 | 内容 |
|------|------|
| `product-manager/AGENT.md:4-5` | `tools: ... user_question`；`disallowedTools: ... agent_dispatch` |
| `product-manager/AGENT.md:34` | Anti-Pattern：「禁止跳过需求澄清直接编写 PRD — 至少执行一轮 user-interview」 |
| `architect/AGENT.md:5,44` | `tools: ... user_question`；「禁止零用户确认完成架构设计 — 至少项目类型和架构风格须经用户确认」 |
| `req-analysis/SKILL.md:29-33` | Step 1 需求收集与澄清：「执行至少一轮 user-interview 确认核心需求方向」 |
| `research/SKILL.md:34-44` | 指令 2 user-interview：工具 = AskUserQuestion，「向用户展示并等待回答…不猜测，收集完再继续」 |

设计明确要求这两个 agent **在自身执行体内**完成多轮交互式澄清。

### 1.2 执行现实：它们是非交互子代理

| 证据 | 内容 |
|------|------|
| `orchestrator/AGENT.md:38-39` | Phase 1 → product-manager；Phase 2 → architect（经 Phase Routing 派发） |
| `agent-dispatch/templates/dispatch-prompt.md:6-10` | 派发即 `Agent tool: subagent_type: "{agent_id}"`，子代理独立上下文运行 |
| `agent-dispatch/SKILL.md:77-79` | 「每个 Phase Agent 作为独立子代理运行，拥有自己的上下文窗口」「子代理无法直接访问调用方的上下文」 |
| `platforms/claude-code/profile.yaml:80-83` | `dispatch: tool_name: Agent, is_async: false`（同步，但同步 ≠ 可交互） |
| `platforms/claude-code/profile.yaml:14` | `tool_map: user_question: AskUserQuestion`——**扁平映射，不区分主线程 vs 子代理** |

`Agent` 工具语义（本会话工具说明同样印证）：子代理最终消息**作为工具结果回传、不展示给用户**。同步派发只意味着主线程阻塞等待返回，**不**意味着子代理能触达用户。这是缺陷的概念根源——**把 `is_async: false` 误当成「可交互」**。

### 1.3 框架内部自相矛盾（这是问题已被半意识到的痕迹）

| 证据 | 矛盾点 |
|------|--------|
| `ORCHESTRATOR-PROTOCOLS.md:112` | 「**前台子代理(默认)可直接使用 AskUserQuestion 向用户提问**。本协议仅在后台子代理返回 needs_input 时触发。」 |
| `research/SKILL.md:36` | 「AskUserQuestion（前台子代理和主线程 Agent 均可直接使用；仅后台子代理需使用指令 2b）」 |
| `dispatch-prompt.md:60-64` + `ORCHESTRATOR-PROTOCOLS.md:111-120` | 但**整套 needs_input → Interrupt-Resume → continuation 回路**又是按「子代理无法直接问、必须回传 needs_input 让 orchestrator 代问」设计的 |

框架**同时**声称「前台子代理可直接问」**和**「子代理回传 needs_input 由 orchestrator 代问」。前者是错误前提（区分「前台/后台」无意义，真正的区分是「主线程 vs 派发子代理」），后者才是 Claude Code 上唯一可行的路径——但它被降格成了 research `指令 2b` 的**降级兜底**，而非主路径。

### 1.4 实际后果（用户观察的机理）

把发散性阶段塞进非交互子代理，触发三种退化：

1. **静默假交互**：子代理被 prompt 要求「执行一轮 user-interview」，但无法真的问到人——只能**幻觉一段访谈**或直接落 `[ASSUMPTION]`，澄清形同虚设。
2. **调研被阉割一半**：research 的 web-search / doc-lookup 在子代理内**可用**（自治工具），但 user-interview 不可用——「广泛调研」缺了与人对齐的一环。
3. **多轮往返被惩罚**：真实需求/架构澄清是 5~10 轮有机问答；若强行走 needs_input 主路径，**每一轮 = 子代理整体拆除 + 全量上下文重新注入 + continuation 重启**（`dispatch-prompt.md:31-33`），高延迟且**有损**（子代理逐轮丢弃头脑风暴上下文，仅文件 + 答案存活）。代价之高，反向激励子代理「少问甚至不问」，与发散阶段的本质对抗。

> 结论：发散/交互密集的早期阶段（PRD、ARCH），与「上下文隔离、非交互、为收敛性生产任务优化」的子代理执行模型**根本不匹配**。子代理模型适合 TDD 这类输入已明确的收敛任务，不适合需要与人共同发散的任务。

---

## 2. 问题 ① 分析：调度协议的文件格式

### 2.1 markdown 是正确载体

- 协议的消费者是 **LLM 本身**（orchestrator 即 LLM），不存在独立解释器。换成 JSON/YAML 状态机/DSL，最终仍要被 LLM 再叙述成自然语言，徒增一层且丢失判断性细节（「何时该问」「如何取舍」无法用纯枚举表达）。
- LLM 对 markdown 的指令遵循度最高（训练分布决定）。
- 协议大量内容是**判断性**的（Revision/Approved-with-Notes/Manual Review 的取舍），天然属于散文。

### 2.2 真正的脆弱点：确定性骨架埋在散文里

`framework-review` B5-α/β（`SKILL.md:55-56,141-143`）已经在**正则解析** orchestrator 的 Phase Routing markdown 表来生成「phase × agent 覆盖矩阵」。这说明：阶段路由表、状态转移、守卫条件这层**确定性骨架本就该是数据**，现在却以散文形式存在、靠脆弱的正则抽取。`framework.json#/features[*].phase_guard`（B5-δ）已是这种「数据化骨架」的雏形，但 Phase Routing 本身尚未数据化。

### 2.3 建议（次要、非阻塞）

不替换 markdown，而是**抽出确定性骨架为单一事实源**：把「phase → agent → skill → 产出 doc_type → 守卫」这张表提升为 `framework.json`（或 `workflow.yaml`）中的结构化声明，markdown 协议以引用方式呈现。收益：① framework-review B5 从「正则解析散文」改为「读结构化数据」，校验更稳；② 路由与守卫成为可被 lint 的契约。判断性散文继续留在 markdown。**此项与问题 ② 解耦，可作为后续独立改进。**

---

## 3. 改进方案（问题 ②）

### 3.1 方案选型

| 方案 | 描述 | 取舍 |
|------|------|------|
| **A. 全程主线程内联** | PRD/ARCH 不派子代理，orchestrator 在主线程「戴 PM/架构师的帽子」直接产文档 | ✅ 交互全可用；❌ 主线程上下文污染严重、与 orchestrator「不直接产业务文档」原则冲突、丢失隔离 |
| **B. needs_input 升为主路径** | 承认子代理不能问，所有澄清走 needs_input → orchestrator 代问 → continuation | ✅ 当前能跑；❌ 逐轮有损 + 高开销，反向激励少问，发散阶段体验差（见 §1.4.3） |
| **C. 发散/收敛分离（推荐）** | 把每个交互密集阶段拆成两段：**发散段**在主线程做、**收敛段**派子代理做 | ✅ 顺着架构纹理；✅ 交互全可用且隔离保留；中等改造量 |
| **D. 能力门控派发** | 新增 profile 能力位 `subagent_interactive`，按平台决定内联 vs 子代理 | ✅ 最「框架正确」可泛化；❌ 改造面最大，宜作为 C 之上的后续泛化 |

### 3.2 推荐：方案 C（发散/收敛分离）

把 Phase 1 / Phase 2 各拆为两段：

- **发散段（主线程 / orchestrator 执行）**：用 research(user-interview/web-search) + AskUserQuestion 在主线程做**完整多轮**头脑风暴与澄清——交互工具在主线程原生可用、无逐轮拆除成本。产出一份中间「**澄清蓝本**」文件（如 `docs/prd/clarification-brief.md` / `docs/arch/decision-brief.md`，status=draft）。
- **收敛段（子代理执行，维持现状）**：派发 PM / architect 子代理，输入**已是完整澄清蓝本**，子代理只需把蓝本结构化成 PRD / ARCH，**无需再交互**——子代理上下文隔离对这段重型文档写作仍有价值。残余小缺口仍可走 needs_input。

这把**发散/交互（主线程）**与**收敛/生产（子代理）**沿任务本质切开，既补上交互缺口，又保留子代理隔离收益。

---

## 4. 可执行步骤

> 下列为方案 C 的最小可行落地序列；每步都是独立可提交单元。术语与命名沿用现有约定。

### Step 1 · 修正错误前提（文档事实纠正，先行且独立）
1. `ORCHESTRATOR-PROTOCOLS.md:112`：删除「前台子代理可直接使用 AskUserQuestion」表述。改为陈述当前事实——**派发子代理为非交互执行体，交互式澄清必须在主线程进行或经 needs_input 回传由 orchestrator 代问**；本协议是子代理回传 needs_input 后的标准路径（不再是「后台兜底」）。
2. `research/SKILL.md:36`：把「前台子代理…可直接使用」改为「**主线程 Agent 可直接使用；派发子代理须经指令 2b 回传 needs_input**」。指令 2b 由「降级兜底」正名为派发子代理下的**常规交互路径**（`research/SKILL.md:44-51`）。
3. 自检：全仓 grep `前台子代理|后台子代理`，统一口径为「主线程 vs 派发子代理」。

### Step 2 · orchestrator 增加「派发前澄清」段
1. 在 `ORCHESTRATOR-PROTOCOLS.md` 的 Phase Routing 热路径中，为 Phase 1（requirements）与 Phase 2（architecture）前置一个 **Pre-Dispatch Clarification** 子协议：orchestrator 在主线程用 research(user-interview) + AskUserQuestion 跑完发散澄清，落 `clarification-brief` 中间文件，再派子代理。
2. agile-lite 的 `planning` 合并阶段、agile-prototype 的 `brief` 阶段同理（这些模式交互需求更集中）。
3. 守卫对齐：该中间文件路径需纳入 orchestrator `allowed_paths`（其为 `[]` 无限制，天然满足）；蓝本 doc_type 不进 doc-review 主门禁（属工作中间产物）。

### Step 3 · PM / architect 契约改写（消费蓝本而非自行访谈）
1. `product-manager/AGENT.md`：Input Contract 增加「必读：澄清蓝本」；Anti-Pattern 第 1 条由「至少执行一轮 user-interview」改为「**禁止脱离澄清蓝本自行编造需求**；蓝本未覆盖的残余缺口经 needs_input 回传，不在子代理内幻觉访谈」。
2. `architect/AGENT.md`：同理，「项目类型/架构风格须经用户确认」改为「须以澄清蓝本中已确认的项目类型/架构风格为准；缺失则 needs_input 回传」。
3. `req-analysis/SKILL.md` Step 1：区分两种入口——主线程调用时正常 user-interview；子代理调用时改为「消费澄清蓝本 + 残余缺口 needs_input」。

### Step 4 · 一致性校验与守卫
1. 跑 `cataforge skill run framework-review -- all`（确认无新增 FAIL/WARN）+ `uv run --extra dev python scripts/checks/run_local.py`。
2. 跑 framework-review Layer 2（`-- agents --target product-manager` / `architect`、`-- skills --target research`）核对改写后 Identity↔Phase、Anti-Patterns 具体性维度。
3. 检查 `dispatch-prompt.md` needs_input 示例（:76-84）与新口径一致（已一致，无需改）。

### Step 5（后续、独立）· 问题 ① 骨架数据化
将 Phase Routing 表（phase → agent → skill → doc_type → guard）抽至 `framework.json`/`workflow.yaml` 结构化声明，framework-review B5 改读结构化源；markdown 协议保留判断性散文并引用之。**与 Step 1~4 解耦，可单独立项。**

### Step 6（可选泛化）· 方案 D 能力门控
为 `platforms/*/profile.yaml` 增 `subagent_interactive: true|false` 能力位，使「内联 vs 子代理」成为平台能力的函数（Claude Code = false → 走 Step 2 主线程发散；若某平台子代理可交互则可跳过）。作为 Step 2 之上的泛化，非必需。

---

## 5. 附：framework-review 静态检查基线

`cataforge skill run framework-review -- all` → **PASS（0 FAIL / 1 WARN / 0 INFO）**。唯一 WARN 为 `reviewer/rules/lang-java.md:9` 裸数值 `>300 行` 未引用 `DOC_SPLIT_THRESHOLD_LINES`，与本议题无关，可在 B4 清理顺手修复。本议题的缺陷属**语义/运行时交互**层面，静态结构检查（B1~B9）不覆盖——这本身也提示：framework-review 当前无「子代理交互能力 × 阶段交互需求」匹配性检查项，可作为 §4 Step 5 之外的守卫增强候选。
