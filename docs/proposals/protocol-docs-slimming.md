# 分析：COMMON-RULES / ORCHESTRATOR-PROTOCOLS 精简与调度协议载体演进

> 状态：分析完成，待评审。同 PR 仅落地既有超长行治理（纯格式、语义零变化）；
> §2–§3 的精简项与 §4 的载体演进均**未实施**，按 §5 实施序独立落地。
> 范围：`.cataforge/rules/COMMON-RULES.md`（319 行 ≈6.4k tokens）与
> `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md`（432 行 ≈8.1k tokens）。
> 方法：两文件全文直读 + 按 H2 节统计行数/token/消费方；载体对比建立在
> `docs/proposals/design-phase-interactivity/analysis.md` 问题①（markdown 载体，非缺陷）
> 的既有结论之上，不重复论证。
> 约束：任何精简不得改变协议语义与调度行为；防腐硬约束 1–3 全程适用。

---

## 1. 数据面：钱花在哪里

两文件都是每次调度重复消耗 token 的 prompt 资产（COMMON-RULES 全员加载；
ORCHESTRATOR-PROTOCOLS 为 orchestrator 热路径，自述「阶段调度热路径协议」，
低频协议已拆去 ORCHESTRATOR-META-PROTOCOLS.md——冷热分层有先例）。按节测量：

| COMMON-RULES 节 | 行 | tok≈ | 消费方 |
| ---------------- | --- | ----- | ------ |
| 框架配置常量 | 52 | 1781 | 全员（但其中 UNATTENDED_* 6 行仅 1 个消费方） |
| 审查报告规范 | 85 | 1528 | 仅 reviewer 系（doc/code/sprint/framework-review） |
| 输出质量原则 | 61 | 882 | 混合（残留/估时全员；保真类 AC 仅 test-writer/qa 系） |
| 执行模式矩阵 | 16 | 420 | orchestrator / product-manager / tech-lead |
| 其余 10 节合计 | 105 | 1766 | 全员通用契约（状态码/分类/引用格式/IO 契约等） |

| ORCHESTRATOR-PROTOCOLS 节 | 行 | tok≈ | 触发频率 |
| -------------------------- | --- | ----- | -------- |
| Project Bootstrap | 39 | 1101 | 每项目一次（冷） |
| Phase Transition Protocol | 52 | 1114 | 每阶段一次（热） |
| Mode Routing Protocol | 38 | 824 | 每次阶段决策（热） |
| Manual Review Checkpoint | 59 | 629 | 命中检查点时（热） |
| Sprint Review Protocol | 29 | 635 | 每 Sprint（热） |
| 4 个恢复协议（Rolled-back/TDD Blocked/Crash/Truncation） | 44 | 778 | 异常路径（冷） |
| 其余各节合计 | 171 | 2974 | 混合 |

结论：**受众错配与冷热混装是主要浪费**——全员文件里躺着单一消费方内容（≈2.4k tok），
热路径文件里躺着一次性/异常路径内容（≈1.9k tok）。散文压缩的空间反而次要。

---

## 2. COMMON-RULES 精简方案（语义零变化的搬运，非删减）

原则：**受众分层**——只被一类角色消费的内容外迁到消费方就近的 reference，
COMMON-RULES 留一行指针；全员契约（状态码、问题分类、三态判定、
verdict_blocking_semantics、文档引用格式、IO 契约）原地不动。

| # | 项 | 动作 | 节约 | 风险与对策 |
| --- | ---- | ------ | ------ | ----------- |
| S1 | §审查报告规范（85 行） | 迁 `.cataforge/references/review-report-spec.md`，常量表位置留指针；front-matter 表与编号规则随迁 | ≈1.4k tok/每次非 reviewer 调度 | 引用锚点分布在多个 SKILL —— deployed-links 守卫与 cross-asset SSOT 检查兜底；分 PR 时先建新文件再改引用 |
| S2 | UNATTENDED_* 6 常量行 | 值仍留常量表（SSOT 不动），**说明列**压为一句，机制细节迁 unattended-building-loop skill | ≈0.2k tok | 双写关系（framework.json#constants）不变，仅动散文 |
| S3 | §保真类 AC 断言（9 行） | 迁 `.cataforge/references/`（与 external-truth-first.md 同族），原地留一行指针 | ≈0.3k tok | 消费方（test-writer/tech-lead/qa）SKILL 已有 references 加载惯例 |
| S4 | 常量表说明列整体瘦身（MID_PROGRESS_LOC 等把触发机制细节留给消费方 SKILL） | 说明列只答「这是什么」，「怎么用」归消费方 | ≈0.3k tok | 逐行核对消费方 SKILL 已含机制描述，避免语义丢失 |

合计可省 ≈2.2k tok/调度（文件 -35%）。**明确不动**：执行模式矩阵（≥3 消费方）、
输出质量原则的残留/估时两节（全员纪律，且是守卫的语义蓝本）。

---

## 3. ORCHESTRATOR-PROTOCOLS 精简方案

| # | 项 | 动作 | 节约 | 风险与对策 |
| --- | ---- | ------ | ------ | ----------- |
| O1 | Project Bootstrap（39 行） | 拆 `ORCHESTRATOR-BOOTSTRAP.md`，热文件留触发行（「{INSTRUCTION_FILE} 缺失 → Read 该文件执行」）；复用 META-PROTOCOLS 拆分先例 | ≈1.1k tok/常规调度 | AGENT.md 资产清单与 framework-update 委托入口同步改；doctor protocol_refs 兜底 |
| O2 | 4 个恢复协议（44 行） | 拆 `ORCHESTRATOR-RECOVERY-PROTOCOLS.md`，热文件留 4 行触发索引表（状态码 → 协议名 → 文件） | ≈0.8k tok/常规调度 | 触发索引必须留在热文件，否则异常时想不起去加载；索引漂移由 links 守卫兜底 |
| O3 | Revision Protocol Step 4 复述增量审查语义后自陈「完整语义以 code-review SKILL 为准」 | 砍复述，留指针 + 一句触发口径 | ≈0.2k tok | 该段自己声明了权威在别处，属自认的重复 |

合计热文件 8.1k → ≈5.9k tok。**权衡后不做**：
把 8 处 ```bash 事件命令块压成单行内联——单行命令普遍 >100 字符，
与行长治理目标冲突，fenced block 是长命令的合法容器；
Manual Review Checkpoint 的三份交互模板——模板文案是 LLM 需要的字面输出物，
压缩会丢 pre_deploy demo 必选项这类门禁语义。

---

## 4. 载体形式对比：调度协议该不该继续用纯文本 markdown

前置事实：`design-phase-interactivity/analysis.md` 问题① 已核实结论——markdown 是
LLM 消费型协议的正确载体（指令遵循度最高），真正的脆弱点是**确定性状态机骨架埋在散文里**；
该结论已兑现为 `framework.json#/workflow`（路由骨架 SSOT，markdown 路由表降为只读视图）。
本节在此之上比较五种载体的适用边界：

| 载体 | LLM 遵循度 | token 成本 | 机器可校验 | 漂移风险 | 交互/判断语义表达 | 结论 |
| ------ | ---------- | ---------- | ---------- | -------- | ---------------- | ------ |
| A 纯 markdown（现状） | 高（编号步骤+表格是 LLM 最强执行形态） | 高 | 弱（靠 4 个 prompt 守卫） | 中 | 强 | 保留为「判断+交互」层载体 |
| B YAML/JSON statechart 全量结构化 | **低**——嵌套结构丢失祈使语气与强调层次，条件分支/用户选项文案塞进字段后可读性反降 | 中 | 强 | 低 | 弱（文案与判断口径必然回退为长字符串字段） | 否决为全量方案 |
| C DSL（mermaid stateDiagram / BPMN） | 中（小图可读，guard/动作细节仍要注释回文本） | 低 | 弱（无 schema 生态；BPMN XML 对 LLM 更差） | 中 | 弱 | 仅作**视图**（`viz framework` 已渲染编排拓扑），不作事实源 |
| D 可执行 CLI 状态机（协议步骤代码化，LLM 只调命令+处理分支） | 高（命令是最强确定性） | **最低** | **最强**（可测试） | **最低** | 不适用（交互分支仍需 prompt） | 确定性步骤链的目标载体 |
| E 混合分层（现行方向深化） | 高 | 低 | 强 | 低 | 强 | **推荐** |

关键论证：协议内容是**两类异质物的混合**——

1. **确定性步骤链**（如 Phase Transition Step 5–9：validate → reconcile →
   doc-consistency → event batch → claude-md check，全是 CLI 调用的固定序列）：
   这类内容放 markdown 是把状态机写成散文让 LLM 逐步转译，每次调度都有漏步/顺序漂移风险。
   正确归宿是**一条复合 CLI 命令**（先例已在仓内：`event log --batch`、
   `claude-md check`、`context reconcile`、Layer 1 脚本化）。终态形如
   `cataforge phase transition`：幂等执行全部确定性步骤、遇分支输出结构化选项让
   LLM 接管，协议段从 52 行缩到 ≈15 行（触发时机 + 分支处置表）。
2. **判断与交互协议**（用户选项路由、恢复决策、澄清口径、模板文案）：
   无法结构化到不失真——「向用户展示…提供选项…选 2 则…」的祈使序列正是 LLM
   遵循度最高的形态，JSON 化后反而要 LLM 先脑内还原成自然语言再执行。
   这一层 markdown 是终态而非过渡态。

**推荐决策**：不换载体；沿 E 深化——确定性骨架继续下沉（常量/路由已在
framework.json；步骤链逐段 CLI 化），markdown 协议收敛为「何时触发 + 分支怎么办」薄壳，
文体统一为编号步骤 + 表格 + 最少散文。**重评条件**：若未来平台提供原生 workflow
执行原语（hook 级状态机），可将 D 层从 CLI 迁移到平台原语；若某段 CLI 化后频繁需要
LLM 中途干预（复合命令拆不开的场景 >2 次/月），该段回退 markdown 并记录原因。

---

## 5. 实施序

| 步骤 | 内容 | 性质 | 依赖 | 优先级 |
| ------ | ------ | ------ | ------ | -------- |
| 本 PR | 既有超长行治理（87 行重排，语义零变化：去空白归一化后与原文逐字节相同，仅 blockquote 续行增 `>` 前缀） | 纯格式 | — | 已落地 |
| P1 | O1+O2 冷热拆分（Bootstrap / 恢复协议族外迁，热文件留触发索引） | 纯文档搬运 | — | 高（零代码、收益 ≈1.9k tok/调度） |
| P2 | S1–S4 受众分层外迁 | 纯文档搬运 | 与 P1 无依赖，可并行 | 高（收益 ≈2.2k tok/调度） |
| P3 | `cataforge phase transition` 复合命令（Phase Transition Step 5–9 代码化）+ 协议段收敛 | 代码 + 测试 + 协议改写 | 建议在 P1 后（协议文件已稳定） | 中（收益最大、成本也最大：新 CLI、幂等语义、分支输出契约、全量测试） |
| P4 | 以 P3 为模板评估 Sprint Review 短路判定、Revision 增量审查基线等下一段步骤链 CLI 化 | 代码 | P3 落地且运行 ≥1 个版本周期 | 低（按 P3 实效决定） |

每步独立 PR、独立回滚；P1/P2 落地时逐引用改锚点，依赖 deployed-links、
cross-asset SSOT、protocol_refs 三个既有守卫兜底完整性。

**明确不做**：不引入 YAML/JSON/BPMN 作为协议事实源；不压缩交互模板文案；
不把 fenced 命令块改单行；不为凑行长指标断开行内命令 code span（结构性豁免：
markdown 表格行、fenced 命令行、整条命令/跨文件链接的行内原子）。
