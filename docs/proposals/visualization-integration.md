# 提案：CataForge 可视化能力集成

> 状态：§A–§I 的 PR-A~G 已全部落地（`viz` 命令面 10 视图 + dashboard / serve / quickstart / status、project-visualization SKILL、orchestrator Sprint 收口焊点、prompt-cli-drift 守卫均在仓）。§J 增量优化（资产目录面板 + 项目健康 KPI 概览）为当前设计，待实施授权。关键决策见 §I 决策记录。
> 范围：新增 `cataforge viz` 命令面，复用既有 KG / doc-index / EVENT-LOG / CORRECTIONS-LOG / agent-skill 资产数据，不新建数据层。渲染分三档递进交付；mermaid 可视化收编进 viz 统一入口；可写编辑器与常驻服务列为远期潜在特性。交付同时覆盖代码、提示词资产、文档资产与守卫的同步面。
> 交付边界：数据源盘点、渲染分档、路线选型、功能评分、模块设计、资产改动面、分阶段 PR 计划与操作步骤为本文职责；实施代码以后续 PR 为准。

---

## 0. 总体判断

CataForge 是 CLI / 文件驱动框架，可视化能力须服从同一定位：**单命令产出、可被版本化的产物、零或极少运行时依赖、复用既有数据**。框架内已有结构化数据（知识图谱、文档索引、事件日志、纠偏日志、agent/skill 资产）全部具备程序化取数入口，可视化只需在其上做薄适配与渲染，不重复造数据层。

渲染采用**单一中间表示（IR）+ 可插拔渲染器**的分层模型，按能力递进分三档交付：

- **档位 1 — 文本发射**：IR → Mermaid / DOT / JSON 文本。零依赖，下游（GitHub / IDE / MkDocs）原生渲染，可内联进文档。
- **档位 2 — 自包含 HTML**：IR → 单文件 HTML，内联 vendored JS（图渲染 + 图表）。无服务进程、零新增运行时依赖（jinja2 已是依赖，JS 随包分发），提供 zoom / pan / filter / search / 联动与指标看板。
- **档位 3 — 本地静态服务**：标准库 `http.server` 托管产物目录 + 文件变更重生成，提供准实时监控。仅用 Python 标准库，无第三方依赖。

三档共享同一套 IR 与 collectors，仅渲染器/服务包装不同。**可写编辑器（拖拽回写数据）与常驻多人实时服务**因需要服务端与数据回写语义、并与 kg-first authoring 反转交叉，列为远期潜在特性（§H），通过既有扩展缝接入，不进核心、不影响零依赖基线。

`viz` 命令本身是确定性 CLI 工具（取数 + 渲染无 LLM 决策分支）；定位为 agentic 能力，经一个薄发现型 SKILL.md（`.cataforge/skills/project-visualization/`，instructional、`user-invocable: false`）暴露给工作流按情境自主选视图，并由 orchestrator 在 Sprint 收口确定性产出健康度看板作保底（见 §I 决策 2），不进 features / capability 注册表。框架内一切 mermaid 可视化收编为 viz 单一入口（见 §I 决策 4）。

---

## A. 数据源盘点表

所有数据源均已有取数入口，可视化只做薄适配并归一到 IR。

| 数据源 | 可视化价值 | 获取方式（编程 / CLI，附 file:line） | IR 形态 |
| -------- | ----------- | -------------------------------------- | --------- |
| KG 追溯链（implements/satisfies/realizes/verifies） | 需求→模块→任务→测试跨层追溯；断链高亮 | `TraceAPI.from_requirement(direction)` [trace.py:53]；`kg trace <ID>` [query.py:416] | Graph |
| KG Feature 覆盖矩阵 | 各 Feature 有无实现 / 测试，质量盲区 | `TraceAPI.bidirectional_coverage()` [trace.py]；`kg trace --coverage` | Graph + Metric |
| KG arch 层实体（Module/Component/API/DataModel + part_of/depends_on） | 下游业务项目系统架构 / 模块依赖图 | `QueryAPI.all_entities(types=...)` + `depends_on()` [query.py:63-380]；`kg query <SPARQL>` | Graph |
| `docs/.doc-index.json` documents.deps | 文档依赖有向图；stale 上游变更染红 | `indexer.find_stale_deps()` [indexer.py:154]；`find_xref_errors()` [indexer.py:261] | Graph |
| doc-index 计数（doc_type/status/orphans） | 文档健康度看板 | `indexer.validate_docs()` [indexer.py:113] | MetricSeries |
| dev-plan 任务 DAG + 关键路径 | 任务依赖、关键路径高亮、Sprint 泳道 | `task_dep_analysis` main [task_dep_analysis.py:54-224]；KG `Task.depends_on` [core_pydantic.py:1447] | Graph |
| SDLC 当前阶段 + 门禁 check | 7 阶段流转进度、门禁状态 | `phase_cmd.evaluate_phase()` [phase_cmd.py:148]；`read_current_phase()` [registry.py:132] | Graph + Metric |
| `docs/EVENT-LOG.jsonl` | 时间线（phase 配对 / verdict / tdd 节奏） | 解析 JSONL；schema [event_log.py:41-88] | Timeline |
| `docs/reviews/CORRECTIONS-LOG.md` | 腐化趋势（按 deviation/phase 分布与累计） | `collect_corrections()` / `upstream_gap_count()` [collectors.py:160,324] | Timeline + Metric |
| agent 资产 frontmatter（name/model_tier/tools/skills） | 编排图 agent 节点 + agent→skill 边 | `AgentManager.list_agents()/skills_for()` [manager.py:43-98] | Graph |
| skill 资产 frontmatter（id/depends/suggested-tools） | skill 节点 + skill→skill 依赖边 | `SkillLoader.discover()` [loader.py:76-266] | Graph |
| orchestrator→phase→agent 路由 | 编排路由层 | framework.json `workflow.modes.*.phases[].role`；`framework_review._discover` [_discover.py:11-97] | Graph |

IR 只有三种闭合形态：**Graph**（节点+边）、**Timeline**（时序事件）、**MetricSeries**（计数/趋势）。任何新数据源都映射到这三者之一，渲染器无需扩展即可消费。

---

## B. 渲染能力边界与分档依据

仅靠 Mermaid 文本在三个维度的能力评分（5=优 … 1=差），解释为何必须分档：

| 维度 | 评分 | 边界 |
| ------ | :---: | ------ |
| 视觉效果 / 布局控制 | 3 中 | 仅自动布局（dagre / 可选 elk）；不可手动定位，连线交叉、标签重叠、间距不可控；无富节点 |
| 大规模 / 自定义样式 | 2 中下 | 默认 `maxEdges=500`、`maxTextSize=50000`；SVG DOM 线性膨胀，无虚拟化 / LOD / 折叠；数百节点后退化 |
| 用户友好性 | 4 良 | 消费者看图零安装（优）；机器生成文本规避了手写错误，但解析错误信息晦涩、标签需转义 |

结论：Mermaid 文本对**中小规模、只读、内联**结构图达「良」，是理想地基；但在**大规模图**、**交互（zoom/pan/filter/search/联动）**、**指标看板（折线/堆叠条/饼）**三处有硬边界。这三处正是档位 2 用自包含 HTML + 富 JS 库补齐的目标，档位 3 再补「准实时刷新」。分档不是三个产品，而是同一 IR 之上能力递进的渲染器。

---

## C. 技术路线与库选型

### C.1 路线对比

| 路线 | 与 CLI 定位适配 | 归属 | 结论 |
| ------ | :---: | ------ | ------ |
| Mermaid 文本发射 | ★★★★★ | 档位 1 默认 | 采纳 |
| Graphviz DOT 文本发射 | ★★★★ | 档位 1 可选 `--format dot` | 采纳（文本零依赖，渲染由用户侧 graphviz 决定） |
| JSON 发射 | ★★★★★ | 档位 1 `--format json` | 采纳（调试 / 外部集成 / 远期 web 入口） |
| 自包含 HTML + vendored JS | ★★★★ | 档位 2 `--html` | 采纳（无服务、零新增运行时依赖） |
| 标准库静态服务 + watch | ★★★★ | 档位 3 `viz serve` | 采纳（stdlib，零第三方依赖） |
| 进程内栅格化（mmdc/PhantomJS→SVG） | ★★ | — | 不采纳（拖 Node/PhantomJS，脆弱重） |
| 常驻数据服务（Streamlit/Dash） | ★★ | 远期 | 见 §H |
| 全栈可写编辑器（FastAPI+React Flow） | ★ | 远期 | 见 §H |

### C.2 档位 2 vendored JS 库选型

按图规模与用途分流，全部 vendor 进包、单文件内联：

| 库 | 用途 | 选用理由 |
| ---- | ------ | --------- |
| Cytoscape.js | 大规模图（KG 全图 / 全量资产图） | vanilla、大图性能与布局算法最强 |
| vis-network | 中等规模交互图（编排图 / arch / 任务） | vanilla 单脚本，物理布局 + 开箱交互，最易 vendor |
| ECharts | 指标看板与时间线（覆盖率 / 腐化 / EVENT-LOG gantt） | 折线/堆叠/饼/甘特齐全，单文件可 vendor |

渲染器按 IR 形态与规模阈值自动选库：Graph 小图走 Mermaid（档位 1）/ vis-network（档位 2），Graph 大图走 Cytoscape.js，Timeline / MetricSeries 走 ECharts。规模切换阈值见 §I 决策 5（默认值 + 经验调参）。

---

## D. 功能候选评分表

评分（价值高优 / 成本低优 / 复用度高优，1–5）：

| # | 功能 | 价值 | 成本 | 复用度 | PR | 理由 |
| --- | ------ | :---: | :---: | :---: | :---: | ------ |
| 1 | 框架编排图 orchestrator→phase→agent→skill | 5 | 2 | 5 | A | 当前零可视化；提取器已在 framework_review |
| 2 | KG 追溯图（全项目） | 5 | 1 | 5 | B | TraceAPI 现成，泛化即可，最高杠杆 |
| 3 | Feature 覆盖矩阵 | 5 | 1 | 5 | B | `bidirectional_coverage()` 直接暴露质量盲区 |
| 4 | 下游 arch 模块依赖图 | 4 | 2 | 5 | B | 复用 QueryAPI；服务下游业务项目核心用例 |
| 5 | 文档依赖图（stale 高亮） | 4 | 2 | 5 | C | doc-index 已含 deps/stale_deps |
| 6 | 任务 DAG + 关键路径 | 4 | 1 | 5 | C | task_dep_analysis 现成，收编统一入口 |
| 7 | SDLC 阶段进度 | 4 | 3 | 4 | D | 组合 phase 评估 + EVENT-LOG |
| 8 | EVENT-LOG 时间线 | 3 | 3 | 4 | D | 审计 / 回顾价值 |
| 9 | CORRECTIONS 腐化趋势 | 3 | 3 | 4 | D | collectors 现成；趋势图需档位 2 |
| 10 | 资产浏览器（目录 + 依赖 + 搜索） | 4 | 3 | 4 | E | 维护者依赖卫生；搜索在 HTML 层最佳 |

10 项全部推荐，按依赖链分入 PR-A~E；档位 2/3 的富渲染与服务在 PR-E / PR-F 统一接入。起步顺序见 §I 决策 1（PR-A → PR-B 优先）。

---

## E. 架构与模块设计

### E.1 设计原则

- **IR 解耦**：collectors（数据→IR）与 renderers（IR→输出）通过三种闭合 IR 形态正交。新增数据源只写 collector，新增格式只写 renderer，互不影响。
- **按复用范围分层**：纯文本渲染器被 runtime（task_dep_analysis）与 interface（kg trace）复用，须落在 `core`（最低层，全栈可向下 import）；HTML 渲染器、collectors、服务仅服务 viz 命令面，落在 `application`。此切分同时满足零冗余与 import-linter 分层契约。
- **prompt 资产最小化**：viz 的发现面收敛为单一薄 SKILL.md（`.cataforge/skills/project-visualization/`，instructional、`user-invocable: false`）+ orchestrator Sprint 收口焊点，不向 §F.2 黑名单中的 agent / skill 主体散加引用（见 §I 决策 2）。
- **小函数**：渲染器/collector 遵循仓库复杂度门（max-complexity 15 / max-statements 60），单一职责、易测。

### E.2 模块布局与层级映射

```
src/cataforge/core/viz/                 # 纯、零依赖、可被全栈向下复用
  model.py            # IR：Node/Edge/Graph、TimelineEvent/Timeline、MetricPoint/MetricSeries、View 联合
  render/
    mermaid.py        # IR → Mermaid 文本（mermaid 可视化的唯一共享渲染核）
    dot.py            # IR → Graphviz DOT 文本
    json_.py          # IR → JSON（稳定外部契约 / 远期 web 入口）

src/cataforge/application/viz/          # 命令面编排，依赖向下合法（→ runtime/domain/core）
  collectors/
    base.py           # Collector Protocol: collect(root, **opts) -> View
    framework.py      #   ← runtime.framework_review._discover + AgentManager + SkillLoader
    assets.py         #   ← AgentManager + SkillLoader（资产目录 + 依赖）
    trace.py          #   ← domain.kg facade（追溯 / 覆盖 / arch）
    docs.py           #   ← domain.docs.indexer
    tasks.py          #   ← runtime task_dep_analysis + domain.kg Task
    process.py        #   ← core.event_log 解析 + phase 评估
    decay.py          #   ← application.feedback.collectors
  html.py             # IR → 单文件自包含 HTML（jinja2 + 内联 vendored JS，按 IR/规模选库）
  registry.py         # name→collector、format→renderer 映射（唯一扩展缝）
  service.py          # generate(view, fmt, opts)；serve(--watch)
  assets/             # vendored cytoscape.min.js / vis-network.min.js / echarts.min.js（pinned，随包分发）

src/cataforge/interface/cli/viz_cmd.py  # 薄 CLI：解析 opts → service.generate / service.serve
```

层级合法性（import-linter 契约 `interface → application → {runtime|domain} → adapter → core → utils`）：

- `core.viz` 仅依赖标准库 → 被 runtime / interface / application 向下 import，零违规。
- `application.viz` → `domain.kg` / `domain.docs` / `runtime`（task_dep_analysis、framework_review、AgentManager、SkillLoader） / `core` —— 全部向下，合法。
- `interface.cli.viz_cmd` → `application.viz` —— 向下，合法。

**mermaid 收编**：`core.viz.render.mermaid` 是全框架唯一 mermaid 渲染核。既有 `kg trace --output mermaid` 与 `task-dep-analysis --format mermaid` 的旧 CLI 表面分阶段迁移到 `viz trace` / `viz tasks` 并弃用（PR-A 内部去重 → PR-B 迁 kg trace → PR-C 迁 task-dep-analysis 并改其 SKILL 契约与 dev-plan mermaid 授权路径），详见 §G 与 §I 决策 4。

### E.3 命令面

```
cataforge viz <view> [--format mermaid|dot|json] [--html] [-o PATH] [filters]
  views: framework | assets | trace [ID] | coverage | arch | docs | tasks
         | phase | timeline | decay | dashboard
  filters: --phase | --doc-type | --depth N | --root ID | --since DATE
cataforge viz serve [--dir docs/viz] [--port N] [--watch]
```

- 默认输出 stdout（pipe 友好，匹配既有 `kg trace`）；`-o` 写文件。
- `--format` 控制文本渲染器；`--html` 走自包含 HTML 渲染器（与 `--format` 互斥）。
- `dashboard` 为聚合视图，仅 `--html` 下有意义，产 index.html 以标签页内联全部视图。
- `serve` 为档位 3：stdlib `http.server` 托管目录；`--watch` 轮询源数据 mtime 变更后重生成产物。

### E.4 产物与打包

- 产物默认写 `docs/viz/<view>.{mmd,dot,json,html}`；`docs/.docignore` 收录 `viz/`，避免被 doc-index orphan 检查计入而使 doctor FAIL。
- 选定稳定文本图（framework / assets，mermaid `.md/.mmd`）提交版本控制供文档站长期展示；HTML 产物由既有 `.gitignore` `docs/**/*.html` 规则保持临时（见 §I 决策 3）。
- vendored JS 位于 `application/viz/assets/`，随 `packages=["src/cataforge"]` 进 wheel，经 `importlib.resources.files("cataforge.application.viz")/"assets"` 读取并内联进单文件 HTML。无需 force-include 或额外打包配置。

---

## F. 资产改动面（代码 · 注册表 · 提示词 · 文档 · 守卫）

落地不止源码：下列同步面已逐项核实，区分 **CI 阻断（必改）** / **贡献规范（必改，PR review 卡口）** / **推荐** / **不需要**。

### F.1 代码与注册表

| 面 | 位置 | 动作 | 等级 |
| ---- | ------ | ------ | ------ |
| CLI 注册 | `main.py:_register_commands()` [main.py:143] | import 列表加 `viz_cmd` | CI 阻断（无此则命令不存在） |
| 顶层 help | `main.py` `cli` group help 文本 [main.py:50-91] | 新增 `VISUALISATION:` 节列 `viz` | 贡献规范（发现性） |
| 产物 orphan 豁免 | `docs/.docignore` | 追加 `viz/` 一行 | **CI 阻断**（产物无 frontmatter → doctor orphan 门 FAIL） |
| 弃用引用守卫 | `doctor/protocol_refs.py:_DEPRECATED_REFS` [protocol_refs.py:29] | 收编后登记旧表面模式（`kg trace --output mermaid`、`task-dep-analysis --format mermaid`），使残留 prompt 引用被 doctor 标记 | 必改（随 PR-B/PR-C 收编） |
| 下游迁移检查 | `framework.json` `migration_checks` [framework.json:182] | 收编后加 migration_check（带 `release_version`）提示下游 scaffold 更新调用 | 必改（随收编发版） |
| framework.json `features` | — | 不登记 | 不需要（viz 非 phase-gated / skill-routed） |
| `CAPABILITY_IDS` / `EXTENDED_CAPABILITY_IDS` [types.py:48-76] | — | 不登记 | 不需要（viz 经 `shell_exec` 调用，非 agent tool capability） |
| COMMON-RULES 常量表（双写 `.cataforge/` + `.claude/`） | — | 不登记 | 不需要（无跨 agent 引用的阈值/路径；规模阈值留渲染器内部，禁硬编码由 code-review 把关） |
| ruff / vulture / 打包排除 | — | 不调整 | 不需要（vendored JS 非 .py；Click 装饰器已被 vulture 豁免；assets 在包树内自动随包） |
| doctor 专项检查 | `doctor_cmd.py:_DOCTOR_SECTIONS` | 可选加 viz 渲染器可达性检查（`gating=False`） | 推荐（非必须） |

### F.2 提示词资产

提示词侧改动有两类：**发现钩子**（让 agent 能向用户提示 viz 能力，§I 决策 2 取 Bootstrap + framework-review 两处）与**收编契约修订**（§I 决策 4 牵动 task-dep-analysis）。任一引用落地，须同步把 `"viz"` 加入 `scripts/checks/check_prompt_cli_drift.py:GROUPS` [check_prompt_cli_drift.py:43] 以获得幻象动词漂移保护。所有改动遵守硬约束 1：仅命令 + 一句用途，无溯源/版本/过程叙事。

| 改动 | 位置 | 性质 | 归属 |
| ------ | ------ | ------ | ------ |
| 发现钩子 | orchestrator Bootstrap 协议，与 `cataforge kg init` / `cataforge context index` 同层 | 加 1 句「可选运行 `cataforge viz framework`」 | PR-G |
| 交叉引用 | `framework-review/SKILL.md` §推荐触发路径 | 加 1 句「可配合 `cataforge viz framework` 比对编排图」 | PR-G |
| 收编契约修订 | `task-dep-analysis/SKILL.md` + dev-plan mermaid 授权工作流（task-decomp / tech-lead 路径） | 把 dev-plan#§2 依赖图的 mermaid 产出改走 `cataforge viz tasks --format mermaid`；task-dep-analysis 保留 `--format json` 分析职责 | PR-C |

**不该碰黑名单**（加 viz 引用构成膨胀/职责越界）：`reviewer/AGENT.md`、`code-review/SKILL.md`、`tech-lead/AGENT.md`、`architect/AGENT.md`、`arc-design/SKILL.md`（文档内嵌 Mermaid，非 viz 命令面）、`ui-designer/AGENT.md`、`qa-engineer/AGENT.md`、`context/SKILL.md`、`framework-walkthrough/SKILL.md`、`rules/COMMON-RULES.md`。（`task-dep-analysis/SKILL.md` 因决策 4 收编而移出黑名单，见上表。）

### F.3 文档资产

`docs/reference/` 与 `docs/architecture/` 已在 `docs/.docignore` 中 → 新增/更新文档**无需 frontmatter、无需重建 doc-index**。

| 面 | 位置 | 动作 | 等级 |
| ---- | ------ | ------ | ------ |
| CLI 总览 + 命令章节 | `docs/reference/cli.md` 命令总览表 + 新增 `## viz` 节 | 增 viz 行；按 PR 增量补 view/serve 参数；收编后标注旧 mermaid 入口迁移 | 贡献规范（contributing.md 明文） |
| CLI 速查 | `docs/reference/quick-reference.md` 速查表 | 加 viz 行 + 链接 | 贡献规范 |
| 分层/职责/源码结构 | `docs/architecture/overview.md`（分层表 + 职责表 + 源码结构块） | 加 `core.viz` / `application.viz` 条目 | 必改（PR-A 引入新包） |
| 可视化架构专题 | `docs/architecture/visualization.md`（新建） | IR 三形态、collector-renderer 正交、数据流、import 合法性、档位递进、vendored 打包、mermaid 收编 | 推荐（PR-E 必须） |
| 文档导航 | `docs/README.md`（Reference / Architecture 表） | 加 visualization 链接 | 随新建文档同步 |
| README 能力 | `README.md` 特性亮点 + 「下一步看哪里」 | 加「可视化洞察」一节 + 命令示例 | 推荐（PR-E 后） |
| 变更片段 | `changelog.d/{PR#}.md` | 每个用户可见 PR 一个 `Added`；PR-B/PR-C 含 `Changed`（标 BREAKING：旧 mermaid 入口迁移） | **CI 阻断**（`check_changelog_fragments.py` 守护；纯文档可 `[skip-changelog]`） |
| 提案状态流转 | 本文件状态字段 | 每 PR 合并后原地追加「已落地」项（仿 kg-first 提案） | 流程 |

### F.4 测试

每个 PR 为其新增 view 补测试；PR-A 新建 `tests/cli/test_viz_cmd.py`（对齐既有 `test_phase_cmd.py` 等），至少含 `viz --help` smoke 与对应 view 的渲染正确性断言。收编 PR（B/C）须更新/迁移既有断言 `kg trace --output mermaid` / `task-dep-analysis --format mermaid` 的测试。属贡献规范（每新命令对应测试）。

---

## G. 分阶段实施计划

依赖链：**PR-A →（PR-B ∥ PR-C ∥ PR-D）→ PR-E → PR-F**，PR-G（提示词发现）依赖其引用的 view 已存在、建议置后。决策 1 取 **PR-A → PR-B 优先**，C/D 随后（可并行）。每个 PR 独立交付与验证，且各自闭合「代码 + 文档 + 测试 + changelog」义务。

### PR-A · viz 基座 + 文本渲染核 + 框架编排图（档位 1 地基）

代码：

1. `core/viz/model.py`：Node/Edge/Graph、Timeline、MetricSeries、View 联合（纯 dataclass）。
2. `core/viz/render/{mermaid,dot,json_}.py`：IR → 文本。
3. `application/viz/{registry,service}.py` 与 `collectors/base.py` Protocol。
4. `collectors/framework.py`：复用 `framework_review._discover` + b5 路由抽 orchestrator→phase→agent→skill → Graph。
5. `interface/cli/viz_cmd.py` 并在 `main.py` 注册 + help 加 `VISUALISATION:` 节。
6. `kg trace` 与 runtime `task_dep_analysis` 内部改调 `core.viz.render.mermaid` 去重；**此 PR 不改两者 CLI 表面**（表面迁移留 PR-B/PR-C，避免引用尚未存在的 viz view）。
资产同步：`docs/.docignore` 加 `viz/`；`docs/architecture/overview.md` 加 core.viz/application.viz 条目；`docs/reference/cli.md` 加 viz 行 + 起 `## viz` 节（framework view）；`quick-reference.md` 加行；新建 `tests/cli/test_viz_cmd.py`；`changelog.d` 加 `Added`。
验证：`cataforge viz framework` 在 mermaid.live / IDE 渲染通过；新增单测断言节点/边集合；既有 `kg trace` / `task-dep-analysis` mermaid 输出回归不变；`cataforge doctor` 通过；`uv run --extra dev python scripts/checks/run_local.py` 通过；import-linter 无新违规。
边界：仅文本渲染 + framework 视图；mermaid 仅内部去重，不动 CLI 表面。

### PR-B · KG 视图：trace / coverage / arch + 收编 kg trace（决策 1 优先；依赖 PR-A）

代码：`collectors/trace.py`（TraceChain → Graph，省略 ID = 聚合全部 root）；coverage（`bidirectional_coverage()` → Graph + MetricSeries）；arch（arch 层实体 + part_of/depends_on → Graph）；注册到 registry；KG 不可达经 facade 既有降级路径提示。收编：`viz trace` 接管 mermaid 可视化，移除 `kg trace --output mermaid` 选项（保留 `kg trace` 的 json/table 分析输出）。
资产同步：`cli.md` `## viz` 补 trace/coverage/arch 并标注 kg trace mermaid 迁移；`protocol_refs.py:_DEPRECATED_REFS` 登记旧 `kg trace --output mermaid`；`framework.json` 加对应 migration_check；测试迁移 kg trace mermaid 断言到 viz trace；`changelog.d` 加 `Added` + `Changed`(BREAKING)。
验证：本仓自身 KG 或 `walkthrough-sandbox/` 跑通；断言覆盖矩阵行数 = Feature 数；KG 缺失优雅降级；doctor 弃用引用扫描通过；run_local 通过。

### PR-C · 结构视图：docs / tasks + 收编 task-dep-analysis（依赖 PR-A）

代码：`collectors/docs.py`（doc-index deps → Graph，stale/xref 标边样式）；`collectors/tasks.py`（复用 task_dep_analysis 拓扑/关键路径/sprint 分组 → Graph）；注册。收编：`viz tasks` 接管 mermaid 可视化，移除 `task-dep-analysis --format mermaid`（保留 `--format json` 分析职责）。
资产同步：`task-dep-analysis/SKILL.md` + dev-plan mermaid 授权工作流改走 `cataforge viz tasks --format mermaid`（§F.2 收编契约修订）；`cli.md` 补 docs/tasks；`protocol_refs.py:_DEPRECATED_REFS` 登记旧 `task-dep-analysis --format mermaid`；`framework.json` 加 migration_check；测试迁移；`changelog.d` 加 `Added` + `Changed`(BREAKING)。
验证：stale dep 染色断言；任务图与 `task-dep-analysis --format json` 节点/边一致；dev-plan#§2 经 viz tasks 产出 mermaid 与迁移前等价；prompt-cli-drift 守卫通过；run_local 通过。

### PR-D · 过程视图：phase / timeline / decay（依赖 PR-A）

代码：`collectors/process.py`（`evaluate_phase` + 当前阶段 → Graph；EVENT-LOG → Timeline，容错丢行）；`collectors/decay.py`（corrections 聚合 → Timeline + MetricSeries）；注册。
资产同步：`cli.md` 补 phase/timeline/decay；测试补；`changelog.d` 加 `Added`。
验证：EVENT-LOG 样本解析无丢行；`viz phase` 结论与 `cataforge phase status` 退出码语义一致；run_local 通过。

### PR-E · 自包含 HTML 渲染器 + dashboard + 资产浏览器（档位 2）

代码：`application/viz/html.py`（IR → 单文件 HTML，按形态/规模选 Cytoscape.js / vis-network / ECharts，内联 vendored JS）；vendor pinned JS 到 `application/viz/assets/`；全部 view 接 `--html`；新增 `dashboard` 聚合视图与 `assets` 资产浏览器（搜索）。
资产同步：新建 `docs/architecture/visualization.md`；`docs/README.md` 加导航；`README.md` 加「可视化洞察」节；`cli.md` `## viz` 补 `--html` / dashboard / assets 与完整参数表；打包冒烟测试；`changelog.d` 加 `Added`。
验证：生成 HTML **断网**离线打开正常、单文件无外链；打包冒烟断言 `importlib.resources` 能从构建 wheel 读到 vendored JS；run_local 通过。

### PR-F · 本地静态服务 viz serve（档位 3）

代码：`service.serve`（stdlib `http.server` 托管 `docs/viz/`）；`--watch`（轮询 KG store / doc-index / EVENT-LOG / CORRECTIONS mtime → 重生成）；`viz serve` 子命令。
资产同步：`cli.md` 补 `viz serve`；测试补（启动/中断/无第三方 import 断言）；`changelog.d` 加 `Added`。
验证：`viz serve --watch` 启动后改源数据，刷新见更新；仅依赖标准库；进程可干净中断；run_local 通过。

### PR-G · 提示词发现钩子（依赖 PR-A 的 framework view，建议置后）

代码/资产：按 §F.2 落地 Bootstrap 发现钩子 + framework-review 交叉引用；同步 `check_prompt_cli_drift.py:GROUPS` 加 `"viz"`；`changelog.d` 可 `[skip-changelog]`。
验证：`run_local.py`（含 prompt-cli-drift 守卫）通过；提示词改动满足硬约束 1；不触碰 §F.2 黑名单。

---

## H. 远期潜在特性

档位 4/5 因引入服务端、第三方重依赖或数据回写语义，不进核心、不影响零依赖基线，作为显式 opt-in 的独立轨道，仅在确有刚需时启动。

| 特性 | 触发刚需 | 形态 | 接入缝（无需改核心） |
| ------ | --------- | ------ | -------------------- |
| 常驻数据看板（实时多人监控） | 团队需要常驻刷新仪表盘 | Streamlit / Dash，独立 extra `cataforge[viz-app]` | 消费 `core.viz.render.json_` 的稳定 JSON 输出 |
| 可写图编辑器（拖拽回写数据） | 浏览器内编辑实体/关系并持久化 | FastAPI + React Flow 前端，独立 extra / plugin | 读经 JSON 入口；写须新增 `viz ingest`：编辑后 IR → 既有 `context ingest` 回流，且**必须先定 kg-first 事实源归属**（图编辑回写 KG 还是 markdown） |

设计上保证远期可达：IR + 稳定 JSON 渲染器已是对外契约，远期 web 应用经 HTTP 消费同一 JSON 即可，collectors 零改动；写回路径通过既有 `context ingest` 接入，与 kg-first 反转协同推进。

---

## I. 决策记录

| # | 决策 | 选项与取舍 | 重评条件 |
| --- | ------ | ----------- | --------- |
| 1 | 起步顺序：PR-A → **PR-B（KG 视图）** 优先，C/D 随后 | 候选 PR-B（KG，复用度最高、下游核心价值）/ PR-C（结构）/ PR-D（过程）/ 并行；取 PR-B 因成本最低杠杆最高 | 若下游对文档一致性或进度审计的诉求高于追溯，可改先 C/D |
| 2 | 提示词发现：**薄发现型 SKILL.md（broad discovery）+ orchestrator Sprint 收口保底焊点** | 候选「完全不动」/「仅 optional 钩子」/「薄 SKILL.md + 焊点」/「散加到各 agent 主体」；定位为 agentic 能力后取「SKILL.md + 焊点」——单一 SKILL.md 即覆盖全 agent 发现、其情境→视图映射承载「定向」语义，焊点保证 Sprint 收口确定性产出，无需触碰 §F.2 黑名单的 agent 主体；optional Bootstrap / framework-review 钩子作为补充保留 | 若 SKILL 描述触发率仍低，再在确有价值的单个 agent（如 reviewer→coverage）定向加引用 |
| 3 | 产物入库：**选定稳定图提交** | 候选「默认 stdout+.docignore」/「选定稳定图提交」/「全部提交」；取折中——framework/assets 等稳定文本图（mermaid `.md/.mmd`）提交供文档站，HTML 由既有 gitignore 保持临时，其余按需生成 | 若文档站需要更多视图常驻，扩大提交集 |
| 4 | mermaid 命令：**收编进 viz 统一入口**（破坏性） | 候选「保留双入口+共享核」/「收编进 viz」；取收编以单一入口、消除歧义。**代价**：移除 `kg trace --output mermaid` / `task-dep-analysis --format mermaid`，牵动 task-dep-analysis SKILL 契约 + dev-plan mermaid 授权工作流 + 弃用守卫 + 下游 migration_check + 测试迁移；分阶段实施（PR-A 去重 → PR-B/PR-C 迁表面）降低单 PR 风险 | 若下游迁移成本过高，可临时保留旧入口为薄 shim 转发到 viz |
| 5 | 超大图阈值：默认中图 vis-network、节点超阈值切 Cytoscape.js，**经验调参** | 阈值不硬编码、不入 COMMON-RULES 常量表，留渲染器内部常量；待 PR-E 用真实图规模标定 | PR-E 实测后若默认阈值不当则调整 |

---

## J. 增量优化：资产目录面板 + 项目健康 KPI 概览

> 前提：§G 的 PR-A~G 已全部落地。本节在既有 IR / collector / renderer 之上沿两条用户主线做增量优化——**主线 A**：开发者在一个面板里管理提示词资产（不翻 SKILL.md/AGENT.md）；**主线 B**：下游用户在 dashboard 首屏一眼掌握项目进度与覆盖性。不新建数据层、不引入运行时依赖、不改变 viz 确定性 CLI 定位、不进 features 注册表。

### J.1 现状 vs 缺口

| 能力 | 现状（file:line） | 缺口 |
| ------ | ------------------- | ------ |
| 资产视图 | `assets` collector 仅输出 id 节点 + agent→skill / skill→skill 依赖边 [assets.py:47-61]；HTML 仅按节点名搜索淡出 [html.py:236-245] | 无 frontmatter 元信息、无 rules 资产、无体量列、无源路径跳转、无清单表格 |
| 资产元数据源 | `SkillLoader.discover()` 已解析 description / depends / suggested_tools / user_invocable / maintainer_only / builtin / path [loader.py:46-67]；`AgentManager.skills_for()` / `get_agent_content()` 可取 AGENT.md frontmatter [manager.py:88-104] | 数据现成但 collector 未携带——IR `Node` 只有 id / label / style，无元数据槽 [model.py:17-25] |
| 体量估算 | `_estimate_tokens`（`len//3`）已存在 [domain/docs/_index_build.py:56] | 未被 viz 复用（application.viz → domain.docs 向下 import 合法） |
| dashboard | 10 个 tab 分页拼接，失败视图降级为错误面板 [html.py:159-196] | 无首屏 KPI 概览层、无 tab 间联动跳转、无图例 |
| KPI 数据 | `evaluate_phase()` [application/phase.py:109]、`_phase_sequence()` [collectors/process.py:24]、`TraceAPI.bidirectional_coverage()`、`validate_docs()` [indexer.py:113]、`collect_corrections()` 全部现成 | 无聚合 collector；各指标只在各自 tab 内可见 |
| 配色语义 | ok/partial/bad 三色语义已一致（`#9f6` / `#ff6` / `#f96`）但 hex 以模块常量散落 5 个 collector | 无单一事实源、HTML 无图例说明色义 |
| 空态引导 | `viz status` 有 `run: <命令>` 提示 [viz_cmd.py:277-281]；`collect_safe` 的 error 自带反引号命令 [registry.py:42-53] | dashboard 空/错误面板只回显原始错误文本，未复用可操作引导 |
| 探针覆盖 | `probe_all` 遍历 `COLLECTORS` 注册表 [service.py:81-95] | 无缺口——新视图注册即被 `viz status` 覆盖，验收依赖此机制 |

结论：两条主线所需数据源与扩展缝全部已存在，改动面收敛为「IR 一个可选元数据槽 + 一个新 collector + html.py 渲染增强 + 配色集中化」，无需新造视图体系或数据层。

### J.2 主线 A · 资产目录面板（assets 视图增强）

1. **IR 扩展（唯一 core 改动）**：`Node` 增可选元数据槽 `data: Mapping[str, object] | None = None`。mermaid / dot 渲染器忽略之（文本输出零回归）；json 渲染器透传（外部契约自然扩展）；HTML 渲染器选择性消费。不新增第四 IR 形态——清单即 Graph 节点的属性投影。
2. **assets collector 增强**（collectors/assets.py）：
   - skill 节点 data：`description · depends · tools(suggested_tools) · user_invocable · maintainer_only · builtin · path(repo 相对) · lines · est_tokens`（正文体量复用 `_estimate_tokens`）
   - agent 节点 data：`description · tools · skills · path · lines · est_tokens`（frontmatter 经既有 `split_yaml_frontmatter` 解析；`model` 字段存在则带上、缺失显示 `—`）
   - 新增 **rules 节点**（第三类资产）：`.cataforge/rules/*.md`，data 含 `path · lines · est_tokens`；rules 不参与 depends 拓扑，无边、样式取第三色
3. **HTML assets 专属面板**（html.py 增 assets fragment，其余视图沿用通用 fragment）：
   - 工具栏：搜索框（同时过滤表格行与图节点，沿用既有淡出机制）+ type 筛选 chips（agent / skill / rules）+ maintainer-only 开关
   - 清单表格：`name · type · 描述 · depends · tools · model · 行数 · est_tokens · path`；体量列可点击排序——暴露体量直接服务框架 token 纪律与防腐（对应 CLAUDE.md「每行都在每次调度消耗 token」）
   - 依赖图：既有 Cytoscape 图保留在表格下方
   - 联动：点击表格行 → 图中对应节点高亮 + 居中；点击图节点 → 表格滚动至对应行并高亮
   - 源码跳转：path 列显示 repo 相对路径，点击复制到剪贴板（`navigator.clipboard`，离线单文件可用；`file://` 直链受浏览器安全策略限制不做主路径），复制后即可粘贴到 IDE / 终端打开
4. **文本档不变**：`viz assets --format mermaid|dot` 输出与现版本一致（回归断言）；`--format json` 自然携带 data，成为脚本消费的资产清单契约。
5. **空态**：未部署项目 collector 返回空图 → `EMPTY`；HTML 面板显示引导「未发现 `.cataforge/` 资产——运行 `cataforge deploy`」（见 J.4 统一空态）。

### J.3 主线 B · 项目健康 KPI 概览（overview collector + dashboard 首屏）

1. **新 collector `overview` → MetricSeries**，注册进 `COLLECTORS`（排注册表首位，`viz status` 首行即见）。KPI → 数据源映射（全部既有入口，不新增数据源）：

   | KPI | 数据源 | MetricPoint（series / label / value） |
   | ----- | -------- | -------------------------------------- |
   | 当前阶段 X/N + 门禁 ok/blocked | `evaluate_phase()` + `_phase_sequence()`（标准模式序列） | `phase / <当前阶段名> / 序列索引`；`phase / gate_ok / 1或0` |
   | 核心文档完成 N/6 | doc-index `documents` 的 doc_type × status 对照 `PHASE_DOC_TYPE`（标准序列 6 类：prd/arch/ui-spec/dev-plan/test-report/deploy-spec） | `docs / <doc_type> / 0缺失·0.5存在·1已approved` |
   | Feature 覆盖率 % | `TraceAPI.bidirectional_coverage()` | `coverage / full·partial·none / 计数` |
   | 断链 / stale 文档数 | `validate_docs()` 的 `stale_deps` 与 `xref_errors` | `links / stale·xref_error / 计数` |
   | 近期腐化趋势 | `collect_corrections()` 按月聚合 | `decay / <YYYY-MM> / 计数` |

   `viz overview` 单命令默认 `--format json`（MetricSeries 无 mermaid 形态是既有边界，帮助文本注明）；`--html` 走既有 ECharts bar。
2. **dashboard 首屏 KPI strip**（html.py）：header 下方一排 stat tiles——`阶段 X/N（ok 绿 / blocked 红）· 核心文档 N/6 · Feature 覆盖 %（副行 partial/none 计数）· 断链/stale 合计（>0 警示色）· 近 30 天纠偏数`。每 tile 可点击跳到对应明细 tab（复用既有 `showPanel`）。KG / doc-index 缺失时对应 tile 显示 `—` + `run: <命令>` 提示，不空白（渐进披露：概览在上、明细在下）。
3. **跨视图跳转**：`initGraph` 增加节点 tap 回调注册与全局 `__viz.focus(panelId, nodeId)`（切 tab + 高亮居中目标节点）。首批只接**coverage → trace**一条（未覆盖 Feature 一键看其追溯链，价值已验证）；机制通用但不做全视图任意互跳矩阵，避免过度设计。
4. **图例与配色集中**：新增 `application/viz/palette.py` 作三色语义单一事实源——`ok/full/门禁通过=绿 #9f6`、`partial/stale=黄 #ff6`、`none/broken/blocked=红 #f96`，加资产三类色（agent 蓝 / skill 绿 / rules 中性）。各 collector 改引常量（hex 不变，纯重构零视觉回归）；dashboard 与单视图 HTML header 下加一行图例条（色块 + 语义词），统一「有实现/有测试/断链/stale」认知负担。

### J.4 统一空态与引导（两主线共享）

1. `viz_cmd._short_hint`（从 detail 提取反引号命令）提升到 service 层共享；dashboard 错误面板由回显原始错误改为「此视图需要的数据还未生成」+ 高亮的 `run: <命令>` 引导——把 `viz status` 已有的可操作体验延续进 HTML。
2. `EMPTY` 面板按视图给一句引导（assets → `cataforge deploy`；timeline → 事件将随工作流推进自动记录；decay → 无纠偏记录是健康信号）。

### J.5 UX 线框（文字描述）

```
dashboard 首屏
┌ header: CataForge viz dashboard ─────────────────────────────┐
│ [阶段 development 6/7 ●] [核心文档 4/6] [覆盖 72% ▸partial 3] │ ← KPI strip，tile 点击跳明细 tab
│ [断链/stale 2 ⚠] [近30天纠偏 5]                               │
├ legend: ●绿 完整/通过  ●黄 部分/stale  ●红 缺失/断链/blocked  ┤
├ tabs: Framework | Assets | Trace | Coverage | Docs | …       ┤
│ (各明细 panel，既有行为)                                      │

assets 面板
│ [搜索_______] (agent)(skill)(rules)  ☐ 含 maintainer-only     │
│ name │type │描述 │depends │tools │model │行·tokens │path 📋   │ ← 行点击 → 图内高亮居中
│ ──────────────── 依赖图（Cytoscape，既有）────────────────    │
```

### J.6 验收点

1. **主线 A**：不打开任何 SKILL.md/AGENT.md，在 assets 面板搜到某 skill 的描述、依赖、工具、行数/est_tokens，点击 path 复制成功；点表格行图中节点高亮。`viz assets --format mermaid` 输出与现版本一致（回归测试）。
2. **主线 B**：dashboard 首屏不滚动、不切 tab 读出：当前阶段与门禁状态、核心文档 N/6、Feature 覆盖 %、断链/stale 数、近期纠偏数；tile 点击落到对应明细 tab；coverage 中未覆盖节点一键跳到 trace 并高亮。
3. **一致性**：全部 collector 的语义色引自 palette 常量（测试断言 collectors 无内联 hex）；dashboard 与单视图均有图例条。
4. **探针**：`viz status` 出现 `overview` 行（probe_all 注册即覆盖）；补一条 registry 完整性测试断言 dashboard 视图列表与 COLLECTORS 同步。
5. **空项目**：无 `.cataforge/`、无 KG、无 doc-index 的 tmp 项目生成 dashboard 成功，KPI tiles 显示 `—` + run 提示，assets 面板显示部署引导，无 traceback。
6. **零依赖**：生成 HTML 断网打开正常、单文件无外链；无新增 vendored JS、pyproject 依赖 diff 为空。
7. **守卫**：每 PR 过 `uv run --extra dev python scripts/checks/run_local.py`；project-visualization/SKILL.md 仅在视图映射表追加一行 `| 项目健康 KPI 概览 | cataforge viz overview |`（满足硬约束 1/2/3）。

### J.7 分 PR 计划（每步独立验收、独立回滚）

依赖链：**PR-V1 ∥ PR-V2 互不阻塞，可并行；PR-V3 依赖两者**。各 PR 自带 TDD 测试与 `changelog.d` 片段。

| PR | 标题（conventional-commits） | 内容 | 验收 |
| ---- | ------------------------------ | ------ | ------ |
| PR-V1 | `feat(viz): overview collector + dashboard kpi strip` | palette.py 集中 + collectors 引常量重构；overview collector + `viz overview` 命令；dashboard KPI strip + tile 跳 tab + 图例条；KPI 空态降级 | J.6 之 2（除跨视图跳转）、3、4、5、6 |
| PR-V2 | `feat(viz): asset catalogue panel` | `Node.data` 槽；assets collector 元数据 + rules + 体量；HTML 清单表格 + 筛选 + 表↔图联动 + path 复制；json 契约与 mermaid 回归测试 | J.6 之 1、5、6 |
| PR-V3 | `feat(viz): cross-view focus + empty-state guidance` | `__viz.focus` 与 coverage→trace 跳转；空/错误面板引导统一（`_short_hint` 共享化）；docs 同步（cli.md `## viz` 补 overview 与交互说明）；project-visualization/SKILL.md 视图表追加 overview 一行 | J.6 之 2（跳转项）、7 |

### J.8 明确不做（红线复述）

- 不加第四 IR 形态、不新建数据层、不新增 vendored JS 库、不引入前端框架 / 3D / 动画
- 不做常驻服务与多人实时（§H 边界不变）；viz 保持确定性 CLI，不进 features / capability 注册表
- 跨视图跳转只接已验证价值的 coverage→trace 一条，不铺任意互跳矩阵；体量列只展示排序，不做门禁（防腐门禁属 anti-rot 守卫职责）
