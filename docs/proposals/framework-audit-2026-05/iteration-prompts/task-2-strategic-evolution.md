# 迭代任务 2 · 战略演进（架构与功能特性增量开发）

> 本文件整体粘贴为一个新 Claude Code 会话的首条指令。请用**多智能体动态工作流（workflow）**完成本任务——这是一项「先再校准路线图、再分增量纵切开发」的战略演进工作，适合 fan-out 设计 → 评分综合 → pipeline 实现 → 综合落盘的编排。
>
> **前置**：本任务以迭代任务 1（纯净基点加固）已完成并合入为前提。开工前先确认基点已加固（任务 1 的「修复对账报告」已落盘、门禁全绿）。

---

## 一、任务目标

在已加固的纯净基点上，沿 [`docs/proposals/framework-audit-2026-05/04-evolution-strategy.md`](../04-evolution-strategy.md) 给出的演进路线图，做**有纪律的增量战略演进**——推进架构与功能特性的演化，而非继续扩张功能面。

核心纪律（来自演进策略 §5.5，本任务的总纲）：
- **精度收口 + 可观测性 + 按需扩展**，不为扩张而扩张；
- **触发式而非预测式排期**：除「主动排期项」与「短期局部第一步」外，所有项绑定明确触发条件，无外部压力不预先投入；
- **优先复用现有基建**，而非另起炉灶；
- **KG schema 稳定性是多条主线的共同前置变量**，是杠杆最高的隐性优先项。

## 二、项目背景

- **CataForge** 是「一份规范、四端部署」的 AI SDLC 工作流框架（Claude Code / Cursor / Codex / OpenCode 四端，native/degraded/skip 三档降级）。引擎层（CLI / deployer / skill runner / hook bridge / KG backend）已稳定且具领域中立潜质；SDLC 语义集中在内容层。两块实验子系统：**KG**（Oxigraph / RDF / SHACL）与 **Penpot**。当前 **Alpha**（0.6.x）。
- **决定性事实**（演进策略 §3.1）：`workflow-framework-generator` 今天就能生成非 SDLC 的完整 `.cataforge/` 并让引擎正常运转——即引擎层**无 SDLC 结构性阻断**，解耦/扩展的剩余工作是「数据层硬编码」而非「引擎层障碍」。这决定了多数战略项应「按需触发、分阶段」而非一次到位。
- **本仓自身是 CataForge 项目（dogfood）**：演进必须保持自托管闭环；配置驱动的改动需配套 upgrade/migration 处理。
- **项目纪律以项目指令文件为准**（新会话已自动加载）：`CLAUDE.md`、`.claude/rules/COMMON-RULES.md`、`.claude/rules/SUB-AGENT-PROTOCOLS.md`。

## 三、输入材料

| 来源 | 用途 |
|------|------|
| [`04-evolution-strategy.md`](../04-evolution-strategy.md) | **主路线图**：§1 现状盘点 / §2 前瞻迭代建议 1–8 / §3 「4a 引擎-领域解耦」选项矩阵 / §4 「4b GUI 可视化」形态矩阵 / §5 总体排序（5.1 立即执行 / 5.2 短期第一步 / 5.3 中期 / 5.4 长期 / 5.5 贯穿原则） |
| [`02-platform-deployment-eval.md`](../02-platform-deployment-eval.md) §三 | 平台验证升档路径（选项 A artifact 断言 / B 守卫前移 / C 最小兜底），及四端验证断崖的结构性议题 |
| [`03-walkthrough-first-run.md`](../03-walkthrough-first-run.md) §4/§6 | 走查能力增强项（observation-rubric、沙盒隔离与 run-id 唯一化、阶段产物存在性硬门槛 W-004 等） |
| 任务 1 的「修复对账报告」 | 基点现状 + 移交本任务的遗留清单（任务 1 标 deferred 的项） |

**路线图是权威方向，但非冻结清单**：基点在任务 1 后已变化，开工前必须对当前 HEAD 再校准（部分项可能已被任务 1 obviated、或前置条件已改变）。报告里的选项矩阵（4a 的 A/B/C、4b 的 A/B/C/D）是决策起点，按推荐倾向选并记录理由，不照搬。

## 四、范围边界与触发纪律

- **主动排期（本任务直接做）**：演进策略 §5.1 中的非缺陷项（如 KG prompt 契约去重）、§5.2 短期局部第一步（doc_type 集合外提到 `framework.json`、静态站点导出入口）、以及报告 02 §三推荐「无条件优先 / 守卫底座先行」的验证升档底座、报告 03 的走查能力硬化。每项做成**完整增量纵切**。
- **触发门控（评估后决定做或 defer）**：演进策略 §5.3 中期项（`event stats` CLI、增强 TUI、跨平台 golden 断言、mypy strict 扩展）与 §5.4 长期项（完整 4a 方案 A 领域插件、Plugin 市场协议、本地 Web 仪表盘、跨项目 EXP 聚合）。逐项核对其触发条件是否已满足：满足或维护者明确指示则纳入；否则产出 **go/no-go 备忘**（触发条件现状 + 建议 + 重评条件）并 defer，不预建。
- **不在本任务**：任务 1 已覆盖的纯缺陷修复；与演进方向无关的零散重构。
- **大件强制上抛**：4a 完整解耦、4b Web/桌面形态、Plugin 市场、跨项目聚合等「需跨包重构 / 牵动发版结构 / 引入异构栈」的项，即便触发条件看似满足，也先以选择题形式向维护者确认 go/no-go（每批 ≤ MAX_QUESTIONS_PER_BATCH），不擅自启动。

## 五、工作原则

**演进纪律**
- **路线图锚定 + 再校准**：以演进策略 §5 排序为锚，开工前对当前 HEAD 复核，剔除已被任务 1 obviated 的项、按新基点重排优先级，产出本任务自己的「优先级增量计划」。
- **增量纵切**：每个特性一条完整纵切（设计 → TDD → 实现 → 评审 → 文档 + 必要的 upgrade/migration），非大爆炸式一次落地。
- **KG schema 稳定是共同前置**：4a 的 KG 维度解耦、4b 的 Web 仪表盘/实体图交互都强依赖 KG 本体稳定。把「推动 KG schema 走向第一个 stable 版本（`runtime_api_version` 升至 2.x）」作为高杠杆隐性项纳入评估——它同时解锁 4a-A 的 KG 维度与 4b-A。
- **架构决策留决策记录**：4a 包边界、4b 界面形态、平台验证档位、KG schema 稳定化等关键选型，用 tech-eval / 决策记录留痕（考虑了哪些选项 / 为何选当前 / 何条件重评），4a/4b 报告已备选项矩阵可直接复用。

**工程纪律**
- **向后兼容**：配置驱动改动（如 doc_type 集合外提）需配 `migration_checks` + `upgrade apply` 迁移路径；尊重既有 upgrade/rollback/sidecar 机制；不破坏下游既有项目升级。
- **复用现有基建**：静态站点复用 `.doc-index.json` + `docs/reviews/` 结构、`event stats` 复用 `feedback.collectors`、golden 复用 `tests/golden/`、doc_type 外提复用 `framework.json.context.kg_active_doc_types`——每个短期项建立在已落地基建上。
- **dogfood 不破**：CataForge 自身是 SDLC 项目，演进后自托管闭环与 CI 必须仍然成立。
- **「最小可行」约束的是冗余而非建设**：新特性合理增码不违背 `CLAUDE.md` §硬约束 1；但仍不堆砌设计残留、不写溯源叙事，遵守硬约束 2（语言解耦）/ 硬约束 3（文档结构）。

**通用纪律**
- 遵守 git/PR 流程：feature branch + PR、conventional-commits 标题（`feat|refactor|build|...`）、squash merge；每个增量独立可评审、可回滚。
- 每次提交前手动跑 `python scripts/checks/run_local.py`。
- 文档/交互中文，代码/CLI/参数英文，枚举值恒英文；不写工时估算。

## 六、推荐的动态工作流方法学

- **Phase 0 · 战略再校准**：重读演进策略 §5 与任务 1 遗留清单对当前 HEAD，逐项核触发条件，产出「优先级增量计划」+ 触发门控项的初步 go/no-go。
- **Phase 1 · 设计 fan-out**：对每个选定增量并行多设计（用报告选项矩阵打分综合），关键选型（4a/4b/KG 稳定化/平台验证档位）产出带决策记录的方案。
- **Phase 2 · 实现 pipeline**：每个增量一条 TDD 纵切 → code-review 评审 → 文档；并行触碰文件的实现用 worktree 隔离；配置/契约变更同步 upgrade/migration。
- **Phase 3 · 综合**：集成、全套门禁全绿、dogfood 自托管完好、配置变更迁移到位；更新演进路线图（已做 / 已 defer / 新触发态）；产出大件的 go/no-go 备忘。

## 七、完成定义（DoD）

- **再校准计划**：基于当前 HEAD 产出的优先级增量计划（含触发门控项的逐项 go/no-go）。
- **已实现增量**：每个增量带测试 + 文档 + 评审 + 独立 PR；配置驱动改动带 upgrade/migration 处理。
- **触发门控对账**：每个中/长期项一条 go/no-go 备忘（触发条件现状 + 处置 + 重评条件）；大件均经维护者确认。
- **全绿门禁**：`python scripts/checks/run_local.py`、完整 `pytest`、`cataforge doctor`、`cataforge skill run framework-review -- all` 通过；dogfood `cataforge deploy` 后部署面与源一致，自托管闭环可跑通。
- **路线图更新落盘**：在 `docs/proposals/` 更新演进路线图，反映新状态与重评条件。
- **决策记录**：关键架构选型（4a 包边界 / 4b 界面形态 / 平台验证档位 / KG schema 稳定化）均有可追溯决策记录。

## 八、红线

- **不为扩张功能面而扩张**（演进策略核心告诫）——增量必须服务于精度收口 / 可观测性 / 按需扩展。
- **触发式排期**：除主动排期项与短期第一步外，不为假想需求预建；大件先上抛 go/no-go。
- **增量保持可逆**：每步独立可回滚，配置变更带迁移路径。
- 不破坏 dogfood 自托管；不引入设计残留/溯源叙事（硬约束 1）；不写工时估算。
