# 迭代任务 1 · 纯净基点加固（架构优化 / 代码重构 / 缺陷修复）

> 本文件整体粘贴为一个新 Claude Code 会话的首条指令。请用**多智能体动态工作流（workflow）**完成本任务——这是一项「先核实、再修复、后对账」的大范围质量收口工作，适合 fan-out 发现 → 对抗性验证 → pipeline 修复 → 综合落盘的编排，而非单线性逐条手改。

---

## 一、任务目标

把 [`docs/proposals/framework-audit-2026-05/`](../) 四份审查报告中**确认为真**的缺陷、腐化与一致性问题逐条**核实并修复**，使本仓收敛到一个**架构良好、实现优秀的纯净基点**：

- 死守卫 / 死代码被消除或修复，不再有「守卫存在但执行层缺席」的空转；
- 自称单一事实来源（SSOT）的表/常量与其消费方重新对齐，可发现性恢复；
- 框架自审工具（`framework-review` B-checks / `doctor`）不再对自身架构演进的接缝结构性失明；
- dogfood 部署面与源保持一致；
- 平台适配层的安全静默放行等 release-blocker 级缺陷被堵死；
- agile-lite × KG-active 主干上「忠实填写却注定 FAIL」的契约矛盾被收敛。

完成后，本仓应成为任务 2（战略演进）可以安心增量开发的干净起点。

本任务**只做缺陷修复 / 重构 / 一致性收口**（让既有承诺重新成立、移除腐化）；**不做**新能力建设与战略演进——那是任务 2 的范畴（见下文范围边界）。

## 二、项目背景

- **CataForge** 是一个「一份规范、四端部署」的 AI SDLC 工作流框架：单一 `.cataforge/` 元资产经 deployer 投放到 Claude Code / Cursor / Codex / OpenCode 四个平台，缺失能力按 native / degraded / skip 三档降级。
- 引擎层（CLI / deployer / skill runner / hook bridge / KG backend）已稳定且具领域中立潜质；SDLC 语义集中在「内容层」（scaffold 数据、Python 内置 skill、KG ontology）。两块实验性子系统是 **KG**（Oxigraph / RDF / SHACL 知识图谱）与 **Penpot** 设计集成。当前处于 **Alpha**（0.6.x），重心是精度收口而非功能扩张。
- **本仓自身就是一个 CataForge 项目（dogfood）**：任何改动必须保持自托管闭环不破。
- **项目纪律以项目指令文件为准**（新会话已自动加载，无需我在此重述）：`CLAUDE.md`（git/PR 流程、提交前静态门禁、Agent/Skill 三条硬约束）、`.claude/rules/COMMON-RULES.md`（统一问题分类 / 归因 / 三态判定 / 框架配置常量 SSOT）、`.claude/rules/SUB-AGENT-PROTOCOLS.md`。

## 三、输入材料

| 报告 | 用途 |
|------|------|
| [`01-implementation-review.md`](../01-implementation-review.md) | 26 条实现层 findings（HIGH 6 / MEDIUM 14 / LOW 6）+ 自审元工具盲区专章 + Phase 0 校准记录 + 对抗性下调/纠偏记录 |
| [`02-platform-deployment-eval.md`](../02-platform-deployment-eval.md) | 四端成熟度矩阵 + 缺口清单（H-1~H-5 / M-1~M-14 / L-1~L-6）；**本任务只取其中缺陷/一致性可点修的部分**，验证升档（A/B/C）留任务 2 |
| [`03-walkthrough-first-run.md`](../03-walkthrough-first-run.md) | agile-lite 端到端走查实测 findings（W-/P-/R-S-/P-S- 系列）；**本任务取其缺陷类**，走查能力增强留任务 2 |
| [`README.md`](../README.md) | 方法学 + Phase 0 校准结论 + 落盘约定（注意已驳回项与已落地修复） |

**报告里的「建议」字段是起点假设，不是判决**：仓库迭代快，逐条以当前 HEAD 重新核实证据是否仍成立；采用最小正确修复，不照搬建议原文。

## 四、范围边界与归类原则

**归类原则**——用「这条改动的性质」判定属哪个任务，而非用 finding 编号：

- **属本任务**：让既有承诺重新成立、消除腐化、恢复正确性/一致性的改动——死代码移除、空转守卫修复、SSOT 对齐、重复消除、原子性/错误处理收口、防御性安全补强、部署漂移自愈、自审盲区堵漏、契约矛盾收敛。
- **属任务 2（不在本任务）**：新增能力面与战略演进——新 CLI 子命令、引擎/领域解耦、可视化、平台行为级 E2E/golden 基建、跨项目聚合、插件市场、走查 skill 的 rubric 能力增强等。
- **模糊地带处置**：若某 finding 的修复需要一个**产品方向决策**（典型如 W-001/W-002/W-003：agile-lite 的 lite 文档该如何通过 doc-review，报告各给了两个选项），优先在报告已列选项内选**风险最小、最符合项目纪律**的一项收敛，并在对账报告留决策记录（考虑了哪些选项 / 为何选当前 / 何条件重评）；若选项之间分歧实质牵动演进方向，则**上抛维护者**做选择题（每批 ≤ MAX_QUESTIONS_PER_BATCH），不擅自猜测。

## 五、问题域概览（定位用，非修复方案）

下列为各报告自身的聚类结构，仅供 fan-out 验证阶段定位「工作在哪里」，**每条都必须对当前 HEAD 重新核实**（部分可能已被修复，如 R-S2 已在审查分支落地）：

- **死守卫 / 死代码**：报告 01 的 R-006 / R-012 / R-020 / R-008 / R-014 / R-019。
- **SSOT 漂移**：R-013 / R-015 / R-016 / R-025 / R-028。
- **自审元工具盲区（根因聚焦）**：R-021~R-026 / R-029——报告 01 §自审元工具盲区已给出根因收敛路径（接缝在「skill 从 data-driven 迁到 Python builtin」处），优先做根因修复而非逐点打补丁。
- **原子性 / 错误处理**：R-001 / R-007 / R-011 / R-027。
- **重复 / 一致性**：R-002 / R-003 / R-009。
- **防御性安全**：R-010 / R-026。
- **部署漂移（含需要跑一次 deploy 的自愈）**：R-018 / R-023。
- **平台侧缺陷类**：报告 02 的 H-1（opencode guard_dangerous 静默放行，安全 release-blocker，无条件优先）/ H-2（cursor Write 工具冲突）/ M-6 / M-7 / M-12 等「声明矛盾可静态检测或可点修」的缺陷。
- **agile-lite × KG-active 文档评审系统性失败**：报告 03 的 W-001 / W-002 / W-003（含产品方向决策，按 §四 模糊地带处置）。
- **其余走查缺陷**：R-S1（doctor `kg_ingestion_completeness` 门与 importer 对 `cf:entity_id` 契约不一致，HIGH，报告明确要求**先定点复核 `doctor/kg_ingestion.py` 再排期**）/ W-005 / W-006 / R-S3 / R-S4 / P-S1。

## 六、工作原则

**核实纪律（最重要）**
- **对抗性优先**：报告是输入假设不是结论。每条 finding 交独立怀疑者复核——证据是否对得上当前 HEAD、是否可复现、是否已被现有机制缓解或已修复、原始 severity 是否仍成立。证据对不上即驳回并记录，不凑数、不硬修。
- **尊重既有校准**：报告 Phase 0 已驳回的项（如 src/ 下「空残留顶层包目录」实为零 git 跟踪、本地 `.claude/` 陈旧 ≠ 已提交的仓库缺陷）不得重新当缺陷处理；已记录的对抗性下调/纠偏结论予以沿用。
- **收敛互斥项**：报告中明确互斥的 finding（如 R-012「改 path」与 R-020「直接删除」二择一、R-014 与 R-013 的删/补联动）必须收敛为单一处置，不能两头都改。

**修复纪律**
- **最小正确修复**：贴合 `CLAUDE.md` §硬约束 1（最小可行修改、零设计残留/溯源叙事）、§硬约束 2（与编程语言解耦）、§硬约束 3（文档结构）。改 `.cataforge/` 元资产时尤其克制。
- **回归测试随修复落地**：每个缺陷修复配能复现该缺陷的测试——尤其「死守卫」类，补一条「守卫此前永真/永静默通过」会被它抓住的测试，防止回归。仓库重 TDD，遵循既有测试组织。
- **根因优先于点修**：自审盲区一类（B3 不感知 builtin-only skill 等）优先修根因，使一批从属 finding 一并消解，避免接缝在其他维度继续漏检。
- **决策留痕**：非平凡选择（互斥收敛、模糊地带选项）在对账报告记录可追溯理由。

**通用纪律**
- 遵守 `CLAUDE.md` git/PR 流程：feature branch + PR、conventional-commits 标题（`fix|refactor|chore|test|...`）、squash merge；按子系统或收敛簇合理分组 PR。
- **每次提交前**手动跑 `python scripts/checks/run_local.py`（一条命令跑齐全部 repo-wide 静态守卫；本会话未挂 git hook）。
- 输出语言：文档/报告/交互用中文，代码/CLI/框架参数用英文，枚举值恒英文。
- 不写任何工时估算（`CLAUDE.md` 全局约束）。

## 七、推荐的动态工作流方法学

按需裁剪，但建议这条骨架（pipeline 为默认，仅在需要全量结果做去重/收敛时设 barrier）：

- **Phase 0 · 校准**：对当前 HEAD 抽样复核报告中若干高 severity 锚点是否仍成立（仿报告自身的 Phase 0），修正偏差，确立「已确认 / 已修复 / 已驳回」基线。
- **Phase 1 · 并行核实（fan-out + 对抗性验证）**：按问题域聚类，并行派怀疑者对每簇 finding 逐条复核证据 + 给裁定（confirmed / already-fixed / rejected+证据 / severity-shift / 需维护者决策）。结构化输出便于汇总去重与互斥收敛。
- **Phase 2 · 修复（pipeline）**：每条 confirmed finding 走「修复 → 加回归测试 → 自审（code-review 视角）」纵切；并行触碰文件的修复用 worktree 隔离避免冲突；根因类先修根因再消解从属项。
- **Phase 3 · 综合**：跨簇一致性收尾，跑全套门禁（见 DoD），对 R-018 执行 `cataforge deploy` 自愈并确认 dogfood 部署面干净，落盘修复对账报告。

## 八、完成定义（DoD）

- **逐条裁定**：报告每条 finding 都有明确归宿——confirmed→已修复 / already-fixed（空操作，附说明）/ rejected（附驳回证据）/ deferred（附理由，如「属任务 2」或「待维护者决策」）。无遗漏、无凑数。
- **回归测试**：每个修复带测试；死守卫类附「能抓住原漏检」的测试。
- **互斥收敛**：所有互斥 finding 收敛为单一处置。
- **全绿门禁**：`python scripts/checks/run_local.py`、完整 `pytest`、`cataforge doctor`、`cataforge skill run framework-review -- all` 均通过；dogfood `cataforge deploy` 后部署面与源一致。
- **对账报告落盘**：在 `docs/proposals/`（tracked，纯 markdown）落一份「纯净基点修复对账」，按原 finding ID 列裁定与对应改动，含决策记录与遗留项（移交任务 2 的清单）。
- **PR 合规**：标题 conventional-commits，分组合理，描述承载变更说明（变更叙事进 PR/commit，不溢出到 SKILL/AGENT/源码主体）。

## 九、红线

- 不破坏 dogfood 自托管闭环。
- 不越界进入任务 2（新能力 / 战略演进）。
- 不向 SKILL.md / AGENT.md / 协议文档 / 源码主体引入设计残留或溯源叙事（硬约束 1）。
- 不写工时估算。
- 不在证据对不上时硬修——驳回并记录优于制造虚假修复。
