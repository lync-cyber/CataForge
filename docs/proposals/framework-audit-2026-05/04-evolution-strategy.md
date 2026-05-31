# CataForge 产品演进策略备忘

## 1. 现状盘点

CataForge 已是一个功能完整、自维护闭环成熟的「一份规范、四端部署」AI SDLC 工作流框架。当前能力可归为三层。

### 1.1 核心能力（已稳定）

- **初始化与部署**：`bootstrap`（scaffold→deploy→doctor 幂等编排）/ `setup` / `deploy` 四平台投放（Claude Code / Cursor / Codex / OpenCode），平台适配矩阵覆盖 10 个 `CAPABILITY_IDS` + 4 个 `EXTENDED_CAPABILITY_IDS` + 17 个 `PLATFORM_FEATURES`，缺能力按 native/degraded/skip 三档降级。分层 Override（project/user 两层 + section patch）已落地。
- **升级与版本管理**：`upgrade check/apply/rollback/verify`，增量刷新保留 runtime/state，冲突生成 `*.sidecar`，回滚基于 `.backups/` 快照且可逆。
- **环境诊断**：`doctor` 多段聚合，命中任一 FAIL 即非零退出，作为 CI gate；覆盖 runtime_api_version、16 条 migration_checks、协议脚本可达性、docs validate、KG ingestion completeness、hook importability、8 个内置 skill 可达性、EVENT-LOG schema、CLAUDE.md hygiene、deploy integrity。
- **SDLC 全流程编排**：`start-orchestrator` 驱动七阶段；三种执行模式（standard / agile-lite / agile-prototype）；13 个专角色 Agent；人工检查点 `MANUAL_REVIEW_CHECKPOINTS` 可配置。
- **TDD 引擎**：RED→GREEN→REFACTOR 四档模式（standard / light-dispatch / light-inline / prototype-inline）；Mid-Progress Drop Contract 防 truncation；条件触发 REFACTOR。
- **文档与上下文管理**：`docs load`（按 `doc_id#§N` 精准加载 + `--with-deps` + `--budget`）；`context write/finalize/ingest/reconcile` KG-first 写入生命周期；`doc-gen` 模板实例化与超阈值拆分。
- **双层审查体系**：`doc-review` / `code-review` / `sprint-review` / `doc-consistency` 四条审查线，统一 Layer 1（Python 静态）+ Layer 2（AI 语义）双审，配套短路规则与 Adaptive Review 反向降级。
- **钩子系统**：`hooks.yaml` → 平台原生 hook 桥接，9 个内置 hook 脚本覆盖纠偏捕获、危险拦截、lint、调度日志、通知、result 校验。
- **MCP 与插件管理**：`mcp list/register/start/stop`、`plugin list/install/remove`（entry_points + 本地目录双来源）。
- **事件日志系统**：`docs/EVENT-LOG.jsonl` 统一 JSONL + schema 约束 + doctor 双守卫（schema 校验 + 旁路写入守卫）。

### 1.2 元能力（自审自维护，已稳定）

`framework-review`（B1~B7 七组 Layer 1 子检查 + Layer 2 语义）、`platform-audit`（8 维度能力对账）、`self-update`（check/apply/verify + pip/uv 双包管理器）、`claude-md-hygiene`（大小 + Learnings 条目上限）、`framework-issue-resolve`（GitHub issue 全闭环，维护者专用）。

### 1.3 自学习闭环（已稳定）

On-Correction Learning（三条触发通路写 CORRECTIONS-LOG + EVENT-LOG）、Retrospective（`hard+review` self-caused ≥ `RETRO_TRIGGER_SELF_CAUSED` 触发 reflector）、框架反馈回流（`feedback bug/suggest/correction-export` 四 sink）、Adaptive Review（连续清洁任务自动降级）。

### 1.4 两块实验性子系统

- **知识图谱（KG）**：Oxigraph（RocksDB / RDF / SHACL）后端，`kg init/import/export/validate/reconcile/query/trace/compare-read/write` 全套；`kg-ask` 自然语言追溯；KG-file 双路透明路由（active doc_type 走 KG，其余走 file slice，Agent 调用面不变）。这是后续两个评估议题（4a / 4b）的核心变量——它既是最深的 SDLC 语义绑定点，也是最有价值的可视化数据源。
- **设计工具集成 Penpot**：SaaS / 自托管双模式；`penpot-sync/implement/review` 三 skill 围绕 Token 三方同步与设计-代码一致性。

### 1.5 数据资产

`framework.json`（16 条 migration_checks + 11 features + 3 dispatcher_skills + AGENT_MODEL_DEFAULTS + context.strategy 路由）、4 份 `profile.yaml`、三档 SDLC 文档模板集、schema 集合（含 SHACL shapes）、26 个 Skill 数据驱动包（稳定/实验混合）。`pyproject.toml` 把整个 `.cataforge/` force-include 进 wheel 为 `cataforge/_dot_cataforge/`，SDLC scaffold 随 pip 包发行。

### 1.6 成熟度判断

引擎层（CLI / deployer / skill runner / hook bridge / KG backend）已稳定且具备领域中立潜质；SDLC 语义集中在「内容层」（scaffold 数据、8 个 builtins、KG ontology）。两块实验性子系统（KG、Penpot）是当前主要的不确定性来源与演进杠杆。整体处于 Alpha 阶段——功能广度足够，下一步重心应从「加功能」转向「精度收口 + 可观测性 + 按需扩展」。

---

## 2. 前瞻迭代建议

按「优先级倾向」排序。复杂度用「单点改动 / 涉及多文件 / 需跨包重构」三档表达，不含工时。每条标注用户价值与触发条件。

### 2.1 高优先级：已确认真实缺陷的最小化修复组合

这两条针对**已校准为真**的空转守卫缺陷，范围极小、风险极低、互补，建议同批落地。

**建议 1 · Migration Check 路径存活性可见性（运行时）**
- **缺陷**：`mc-0.1.5-session-context-simplified` 指向已迁走的 `src/cataforge/hook/scripts/session_context.py`（真实文件在 `runtime/hook/scripts/`），且 `allow_missing:true` → 永远静默 SKIP，是空转死守卫。
- **价值**：让 `doctor` / CI 的 migration_checks 真正暴露框架自身重构漂移，而非默默 SKIP 本应覆盖的路径。
- **复杂度**：单点改动。对每条 `allow_missing:true` 且 path 不存在的 check 增加 `WARN` 报告通道（不改行为语义，只增可见性）。可选引入 `expected_absent:true` 字段区分「已知可缺失」与「被迁走的死目标」。
- **触发条件**：随时可做；下次 migration_checks 有新增/修改时同步处理。

**建议 2 · CI 守卫：`mc-*` 路径存活性静态检查（pre-commit / CI）**
- **价值**：与建议 1 互补——建议 1 是运行时可见性，本条是提交时静态拦截，防止新空转守卫被引入。
- **复杂度**：单点改动。新增 `scripts/checks/check_migration_check_paths.py`，对 `allow_missing:false`（或缺省）的 check 验证 path 指向真实文件，对 `allow_missing:true` 的打 WARN；并入 `run_local.py` 与 test.yml anti-rot 步骤。与现有 13 个守卫结构完全一致。
- **触发条件**：与建议 1 同批。

### 2.2 中高优先级

**建议 3 · KG prompt 契约去重**
- **价值**：`is_active_for` 分发决策在代码层是单一事实来源，但其自然语言表述被重复到至少 5 处（doc-nav / doc-consistency / doc-review / task-dep-analysis / COMMON-RULES）。去重后维护者只在一处更新分发策略，下游 skill 作者无需理解 KG 细节，且削减每次 agent 调用的 token 负担——直接符合 CLAUDE.md §硬约束 1「最小可行修改」。
- **复杂度**：涉及多文件。在 COMMON-RULES 用单一段落定义「KG-first 分发透明性原则」，其余各处替换为单一引用；现有「Agent 文档 I/O 契约」段落可从 7 条精简。**不涉及任何 Python 代码**（代码层 facade 已做对）。
- **触发条件**：下次 KG 相关 skill 有文本修改时顺带；或作为独立 chore PR。

### 2.3 中优先级（按需求触发）

**建议 4 · EVENT-LOG 可观测性增强：`event stats` CLI**
- **价值**：当前 14 类事件无聚合分析工具，无法回答「本 Sprint agent 调度次数」「哪个 phase review 循环最多」。增加视图层后，`framework-feedback` 的 `feedback_event_tail` 可从「取最近 20 条」升级为有意义的摘要统计。
- **复杂度**：单点改动到涉及多文件。最简形式 `cataforge event stats [--since]` 读 JSONL 按 event/phase/agent 输出 markdown 表；无新 schema、无新存储。`event_log` 读接口与 `feedback.collectors` 是现成范本。
- **触发条件**：第一个多 Sprint 下游项目上线后（单一小项目体量下分析价值有限，多项目 + correction-export 汇聚时价值放大）。

**建议 5 · 跨平台 E2E golden 断言**
- **价值**：CI 现有 platform dry-run 只验「不崩溃」，不断言产出内容。引入 golden 后能指出「codex deploy 产出的 agent TOML 缺 sandbox_mode 字段」，而非「测试通过但真实平台跑不起来」。
- **复杂度**：涉及多文件。新增 `golden/` 平台 dry-run 期望快照（`tests/golden/` 已有 KG 范例）+ `test_platform_deploy_golden.py` diff + `update_golden.py` 刷新脚本，在 test.yml dry-run 步后加断言。
- **触发条件**：下次平台 adapter 有 CRITICAL/MAJOR 变更后补充（平台快速迭代会缩短漂移窗口）。

### 2.4 中低 / 低优先级（中期，需外部规模或重构契机）

**建议 6 · mypy strict 扩展到 runtime 核心包**
- **价值**：类型错误在 CI 而非下游运行时暴露；对插件开发者/贡献者提供更可信的 public API 契约。
- **复杂度**：涉及多文件。`runtime/skill/runner.py`、`domain/kg/facade.py` 等 strict 化需补 50~100 处注解，渐进式每 PR 扩 1~2 包。test.yml 已预留扩展位。
- **触发条件**：kg / skill 域下次重构时同步推进。

**建议 7 · Plugin 市场协议规范化**
- **价值**：第三方可发布领域专用 agent/skill 包，下游一行 `plugin install` 接入，CataForge 从「单体框架」走向「可扩展平台」。
- **复杂度**：需跨包重构。定义 `cataforge-plugin.yaml` v1 稳定 schema + `plugin list/install` CLI 面 + 开发者文档 + 示例仓库（entry_points 与 PluginManifest schema 已落地，缺 CLI 面与生态协议）。
- **触发条件**：有第一个外部贡献者想发布领域插件时。

**建议 8 · 自学习闭环跨项目汇聚：匿名 EXP 聚合**
- **价值**：多下游项目若在同一 agent 同一 category 反复 self-caused 纠偏，是框架 SKILL.md 本身需改进的信号，可让 reflector 产出更有证据的 SKILL-IMPROVE 建议。
- **复杂度**：需跨包重构。EXP 匿名化 schema + `correction-export --include-exp` opt-in + 上游聚合端 + framework-issue-resolve 读取流程。隐私/匿名化是关键阻碍点。
- **触发条件**：GA 发布 + 10+ 活跃下游项目达到可聚合规模后。

### 2.5 排序总表

| 编号 | 建议 | 优先级 | 复杂度 | 触发条件 |
|------|------|--------|--------|---------|
| 1 | Migration Check 路径存活性可见性 | 高 | 单点改动 | 随时可做 |
| 2 | CI 守卫：mc 路径存活性检查 | 高 | 单点改动 | 与 1 同批 |
| 3 | KG prompt 契约去重 | 中高 | 涉及多文件 | 下次 KG skill 文本修改时 |
| 4 | EVENT-LOG `event stats` CLI | 中 | 单点→多文件 | 多 Sprint 下游项目上线后 |
| 5 | 跨平台 E2E golden 断言 | 中 | 涉及多文件 | 下次平台 adapter 重大变更后 |
| 6 | mypy strict 扩展到 runtime | 中低 | 涉及多文件 | kg/skill 域下次重构时 |
| 7 | Plugin 市场协议规范化 | 中 | 需跨包重构 | 有外部贡献者意向时 |
| 8 | 跨项目 EXP 聚合 | 低（中期） | 需跨包重构 | GA + 10+ 活跃下游后 |

建议 1、2 针对已确认真实缺陷，应主动排期；其余按触发条件按需推进，不建议在无外部压力时预先投入。

---

## 3. 「4a 引擎/领域解耦」评估矩阵

**议题**：将「领域中立引擎」与「可插拔 SDLC 领域包」解耦，使引擎可承载非 SDLC 领域（内容创作 / 电商运营 / 研究分析等）。

### 3.1 关键事实

SDLC 语义的内嵌点全部在**内容层**，而非**引擎层**——这是整个评估的支点。已定位 6 个内嵌点，按耦合强度排序：

| 内嵌点 | 位置 | 耦合强度 |
|--------|------|---------|
| pyproject force-include 打包 SDLC scaffold | `pyproject.toml` L115–125 → `core/scaffold.py` | 强 |
| 8 个 SDLC 专用内置 skill | `runtime/skill/builtins/`（`sprint_review` 硬编码 dev-plan 格式、`doc_review.KNOWN_DOC_PREFIXES`） | 强 |
| framework.json constants/features/dispatcher_skills | `MANUAL_REVIEW_CHECKPOINTS` / `TDD_*` / `SPRINT_*` / 13 角色 AGENT_MODEL_DEFAULTS | 强 |
| KG ontology 实体类型映射 | `domain/kg/export/_entity_meta.py` `_ENTITY_TYPE_TO_DOC_TYPE`（32 实体类 → 6 doc_type）+ SHACL schema | **极强** |
| doctor / migration_checks 目录形状 | `interface/cli/doctor/migration.py` + `kg_ingestion.py`（默认集合即 `BUSINESS_DOC_TYPES`） | 中强 |
| workflow-framework-generator | 已能生成任意领域 `.cataforge/` 骨架并被引擎运行 | （反向佐证：引擎层无 SDLC 阻断） |

**决定性证据**：`workflow-framework-generator` 今天就能生成非 SDLC 的完整 `.cataforge/` 并让引擎正常运转——scaffold 拷贝、deployer、hook bridge、skill runner 本身无 SDLC 约束。即解耦的技术基础已存在，剩下的是「数据层硬编码」而非「引擎层结构性障碍」。

### 3.2 价值 / 可行性 / 风险三维

| 维度 | 评估 |
|------|------|
| **价值** | **中（有限）**。正向：scaffold 与引擎松耦合后可独立迭代节奏；下游可只装所需领域包，削减无用 scaffold 的 LLM prompt 上下文。**限制**：`workflow-framework-generator` 已能跳过 SDLC 内容生成，扩展新领域**今天已可行**——引擎层无阻断，解耦的「解锁」价值有限，主要收益是「不再静默携带无用 SDLC scaffold」。 |
| **可行性** | **中-高**。内嵌点集中在数据层硬编码，提取为配置/插件委派属中等复杂度改动，无跨模块结构重构。下游破坏性可控（已有 upgrade apply 机制）。 |
| **风险** | **中**。四个主要风险：① **KG ontology 重构量被低估**（32 实体类 + SHACL 是深层绑定，新领域需重新设计实体模型，非简单提配置——若 KG 对非 SDLC 仅文件模式则可延期）；② migration_checks 维护双轨（领域包与引擎各自一套，path 引用格式需重新约定）；③ 下游既有项目兼容（涉及 scaffold 目录树重组的 upgrade 历史上从未做过）；④ dogfood 闭环复杂化（CataForge 自身是 SDLC 项目，分离后 CI 需同时维护引擎 + SDLC 包）。 |

### 3.3 包边界选项对比

| 选项 | 核心思路 | 引擎改动面 | 下游破坏性 | 版本协调负担 | 与现有 entry-point 一致性 |
|------|---------|-----------|-----------|-------------|------------------------|
| **A · entry-point 插件注册制** | 仿 `cataforge.platforms`，新增 `cataforge.domains` 命名空间，`DomainPlugin` 提供 scaffold_root / builtin_skills / doc_type_map / kg_entity_types / migration_checks | 中（~6 文件，硬编码→插件委派） | 低（新 API，旧调用兼容） | 低（entry-point 自动发现） | **高**（同机制扩展） |
| **B · 配置驱动 domain profile** | 不拆包，仿 `platforms/<id>/profile.yaml` 增 `domains/<id>/domain.yaml`，SDLC 成默认激活的一个 profile | 中（~10 文件，路径参数化） | 低（upgrade apply 迁移） | 极低（单包） | 中（新概念层） |
| **C · Python 子包拆分** | monorepo 拆 `cataforge` + `cataforge-sdlc`（optional dep / namespace package） | 高（包结构重组） | **高**（`pip install cataforge` 不再含 SDLC，须改 `cataforge[sdlc]`） | 高（多包锁定 + 双 wheel CI） | 低（新范式） |

### 3.4 推荐倾向

**短期推荐：方案 B 的局部实施——仅剥离 doc_type 集合。**

最小可行第一步：将 `BUSINESS_DOC_TYPES` / `DEFAULT_DOC_TYPE_MAP` / `KNOWN_DOC_PREFIXES` 从 Python 硬编码迁到 `framework.json`（它们已在 `framework.json.context.kg_active_doc_types` 下有部分声明），让 doctor / KG / doc_review 的 doc_type 集合完全由配置驱动。改动面约 3 个文件，不引入新包或 entry-point，即可让非 SDLC 项目不被 `KNOWN_DOC_PREFIXES` 拦截、sprint_review builtin 也不会对其报错——已实现「领域包扩展 doc_type」的核心价值。

**理由**：`workflow-framework-generator` 生成的非 SDLC 框架今天已能运行（引擎层无阻断），完整解耦的工程投入应在有具体非 SDLC 用户需求时**分阶段**进行，而非预先完成。方案 A 是完整解耦的最终形态（最符合现有 entry-point 模式），但应延后到触发条件满足。方案 C 当前无充分理由。

### 3.5 重评条件

升级到完整方案 A 的触发条件（满足其一即重评）：
- 出现具体非 SDLC 领域用户，明确要求 `pip install cataforge` 不携带 SDLC scaffold；
- SDLC 领域包需要独立于引擎的发版节奏（如 Sprint 规则迭代快于引擎）；
- KG ontology 需针对新领域扩展（否则 KG 相关解耦价值有限，此条是 KG 维度解耦的硬前提）。

方案 C 重评条件：出现独立团队维护领域包的组织边界。

---

## 4. 「4b GUI/可视化」评估矩阵

**议题**：为 CataForge 的数据资产（EVENT-LOG / PROJECT-STATE / KG / docs / reviews / CORRECTIONS-LOG / 配置）引入可视化界面，降低小白门槛。

### 4.1 资产→视图映射

| 资产 | 自然视图形态 |
|------|------------|
| `EVENT-LOG.jsonl` | 时间线/瀑布流（session 行组，phase/status 着色）——对新用户感知价值最高 |
| `PROJECT-STATE.md` | 项目看板（阶段高亮、文档状态矩阵、Sprint 进度条） |
| KG store | 实体关系图（feature/module/task/test_case 节点 + depends_on 边，可筛 doc_type） |
| `docs/` 业务文档 | 文档树导航 + markdown 渲染 + 章节跳转 |
| `docs/reviews/*` | 审查历史列表（verdict badge，CRITICAL/HIGH 红标） |
| `CORRECTIONS-LOG.md` | 订正学习日志（按 root_cause 分类，retrospective 阈值进度条） |
| `framework.json` + `profile.yaml` | 配置预览（常量表、能力矩阵热图、migration_checks 状态） |
| `CODE-SCAN-*.md` | 代码健康度仪表盘（category 饼图、severity 趋势） |

### 4.2 价值 / 可行性 / 风险三维

| 维度 | 评估 |
|------|------|
| **价值** | **中-高，分层**。阅读侧（非技术干系人查看项目状态）与开发者侧（比 CLI 更直观的状态感知）价值明确；EVENT-LOG 时间线与 KG 实体图对所有用户层次都有感知价值。但「降低小白门槛」的边际价值取决于界面形态——重型方案的安装门槛反成新障碍。 |
| **可行性** | **取决于形态**。轻量方案（静态站点 / TUI）与现有纯 Python 栈同构、可行性高；Web 仪表盘需新增 JSON API 层且与 KG schema 耦合（中）；桌面应用技术栈异构（低）。 |
| **风险** | **取决于形态**。核心风险是**与 KG schema 演化耦合**——KG ontology 仍频繁变动期间，依赖实体图查询的方案 API 层易腐化。其次：Windows `http.server` 端口冲突、前端 JS 无测试覆盖、Textual 0.x API 变动、静态站点实时性差。 |

### 4.3 界面形态选项对比

| 形态 | 技术取向 | 新依赖 | 降低小白门槛 | 维护成本 | 风险 |
|------|---------|--------|-------------|---------|------|
| **A · 本地只读 Web 仪表盘** | `cataforge dashboard` 起内置 HTTP（标准库 / waitress），封装 `docs load` / KG `QueryAPI` / `event_log` 为 JSON API；前端单文件 HTML + Alpine.js + Chart.js + vis-network | waitress（可选，标准库 fallback） | **高** | **中**（需维护 JSON API 层 + 前端 JS，与 QueryAPI 耦合） | **中**（KG/本体演化破坏查询；端口冲突；前端无测试） |
| **B · 增强 TUI（Textual）** | `cataforge tui`，看板/文档树/事件 DataTable/SPARQL 输入框，终端内运行，SSH/tmux 友好 | textual（~3MB，无 C 扩展，optional） | **中**（开发者友好，纯小白仍有终端认知负担） | **低-中**（同语言同进程，无 HTTP 层） | **低-中**（Textual 0.x API 变动；功能易膨胀） |
| **C · 静态站点导出（MkDocs）** | `cataforge export-site` 把 docs + reviews + EVENT-LOG 渲染为静态 HTML，KG 图预渲染 SVG，可托管 GitHub Pages | mkdocs-material（仅 export 可选依赖） | **最高（阅读侧）**（开 URL 即看，零安装） | **低**（只读快照，mkdocs 成熟） | **低**（无实时性，快照延迟） |
| **D · 重型桌面应用（Electron/Tauri）** | 完整 GUI，子进程/JSON-RPC 桥接 QueryAPI，打包 .exe/.dmg | Electron ~150MB / Tauri Rust 栈 | 理论最高，但安装包体积反成门槛 | **极高**（双语言运行时 + 跨进程协议 + 打包 + 自动更新，与纯 Python 栈异构） | **极高**（双栈维护，与仓库单 Python 约束不符） |

### 4.4 推荐倾向

**短期推荐：形态 C 静态站点导出。**
- 零新运行时依赖进 core（mkdocs-material 进 `optional-dependencies[docs]`）；
- 现有 `.doc-index.json` + `docs/reviews/` 结构可直接映射 MkDocs 导航树，适配工作量最小；
- 立即解决「小白阅读项目文档」问题，**不需等 KG schema 稳定**。

**中期推荐：形态 B 增强 TUI。**
- textual 进 `optional-dependencies[tui]`，不影响 core 安装体积；
- EVENT-LOG 的 DataTable 实时浏览对 orchestrator 调试价值明显，直接复用 `event_log` 读取逻辑；
- 维护路径与现有 `cli/ui.py` 渲染层对齐，无需学习前端工具链。

形态 C + B 组合命中「降低小白门槛 vs 维护成本」的最高效点：C 覆盖完全不会用命令行的干系人（维护成本最低，可 CI 定期刷新推 Pages），B 覆盖会用终端、想要比 CLI 更直观的开发者。**形态 D 在任何权衡维度下都不应在 Alpha 阶段进入 backlog。**

### 4.5 重评条件

**推迟评估形态 A 本地 Web 仪表盘**，重评触发条件（建议全部满足）：
- KG schema（`domain/kg/_schema_axioms.py` 本体）完成第一个 stable 版本（`runtime_api_version` 升至 2.x）；
- `QueryAPI` 实体类型枚举（feature/module/component/page/api/task/test_case）不再频繁变动；
- 实际收到用户反馈表明 TUI + 静态站点无法满足可视化需求（尤其 KG 实体图交互）。

**形态 A 价值最高但维护成本也最高**，且与 KG schema 强耦合——应在 KG ontology 稳定后再投入，避免 API 层在本体演化期持续腐化。

---

## 5. 总体建议与排序

CataForge 处于 Alpha 阶段，功能广度已足，演进重心应是**精度收口 + 可观测性 + 按需扩展**，而非继续扩张功能面。两条主线（4a 解耦 / 4b 可视化）的共同结论是：**引擎/数据层已具备扩展基础，但完整投入应由具体外部需求触发，短期只做改动面极小、价值即时兑现的局部第一步。**

### 5.1 立即执行（已确认真实缺陷 + 即时价值，主动排期）

| 序 | 动作 | 来源 | 复杂度 | 说明 |
|----|------|------|--------|------|
| 1 | Migration Check 路径存活性可见性（WARN 通道） | 建议 1 | 单点改动 | 修复已校准为真的空转死守卫 `mc-0.1.5-session-context-simplified` |
| 2 | CI 守卫 `check_migration_check_paths.py` | 建议 2 | 单点改动 | 与 1 同批，防新空转守卫引入 |
| 3 | KG prompt 契约去重 | 建议 3 | 涉及多文件 | 纯 prompt 层，token 效率 + 可维护性，符合 §硬约束 1 |

### 5.2 短期局部第一步（改动面极小，验证扩展方向）

| 序 | 动作 | 来源 | 复杂度 | 说明 |
|----|------|------|--------|------|
| 4 | 剥离 doc_type 集合到 framework.json | 4a 方案 B 局部 | ~3 文件 | 解耦的最小可行第一步，即时兑现「领域扩展 doc_type」核心价值 |
| 5 | 静态站点导出 `cataforge export-site` | 4b 形态 C | 涉及多文件 | 可视化最低成本入口，不依赖 KG schema 稳定 |

### 5.3 中期（按触发条件推进，不预先排期）

| 序 | 动作 | 来源 | 触发条件 |
|----|------|------|---------|
| 6 | EVENT-LOG `event stats` CLI | 建议 4 | 多 Sprint 下游项目上线后 |
| 7 | 增强 TUI `cataforge tui` | 4b 形态 B | 静态站点已落地，开发者侧需求明确后 |
| 8 | 跨平台 E2E golden 断言 | 建议 5 | 下次平台 adapter 重大变更后 |
| 9 | mypy strict 扩展到 runtime | 建议 6 | kg/skill 域下次重构时 |

### 5.4 长期（需外部规模或 GA，慎防过早投入）

| 序 | 动作 | 来源 | 重评条件 |
|----|------|------|---------|
| 10 | 完整 4a 方案 A（entry-point 领域插件） | 4a 方案 A | 具体非 SDLC 用户 / 独立发版节奏 / KG 需跨领域扩展 |
| 11 | Plugin 市场协议规范化 | 建议 7 | 第一个外部插件贡献者意向 |
| 12 | 本地 Web 仪表盘 `cataforge dashboard` | 4b 形态 A | KG schema stable（runtime_api_version 2.x）+ 实体枚举稳定 + TUI/站点不满足 |
| 13 | 跨项目 EXP 匿名聚合 | 建议 8 | GA + 10+ 活跃下游 |

### 5.5 贯穿性原则

1. **真缺陷优先于新功能**：建议 1/2 是唯一应主动排期的代码改动，针对已校准为真的空转守卫，范围与风险都最小。
2. **KG schema 稳定性是两条主线的共同前置变量**：4a 的 KG ontology 解耦与 4b 的 Web 仪表盘 / 实体图交互都强依赖 KG 本体稳定。建议把「推动 KG schema 走向第一个 stable 版本（runtime_api_version 2.x）」作为隐性优先项——它同时解锁 4a-A 的 KG 维度与 4b-A，是杠杆最高的单点。
3. **触发式而非预测式排期**：除 5.1 / 5.2 外，所有项均绑定明确触发条件（外部用户需求 / 下游规模 / 重构契机 / 平台变更），不在无外部压力时预先投入——避免为假想需求承担解耦与双栈维护的长期成本。
4. **优先复用现有结构**：静态站点复用 `.doc-index.json`、event stats 复用 `feedback.collectors`、golden 复用 `tests/golden/`、doc_type 剥离复用 `context.kg_active_doc_types`——每个短期项都建立在已落地基建上，而非另起炉灶。
