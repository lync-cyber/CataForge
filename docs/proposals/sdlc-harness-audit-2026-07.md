# CataForge 面向 LLM 主力开发的 SDLC 能力审查（2026-07）

> 状态：审查已完成，高置信度改进已随本 PR 落地（§7），剩余差距组织为垂直改进 Sprint（§8）。
> 范围：全仓事实核验（src / .cataforge / tests / CI / docs），基线 revision `b5013ed`，14 个审查维度成熟度评分，改进实施与证据包。
> 方法：先事实重建（并行探底 + 逐条实证复核，禁止按文件名推断能力），再评分归因，再实施可独立验收的改进切片，每切片即时跑测试。
> 相关 ADR：[adr-kg-write-guards-and-shacl-shipping.md](../architecture/adr-kg-write-guards-and-shacl-shipping.md)。

---

## 1. 核心判断

CataForge 已经**远超"Prompt 工作流框架"的范畴**：它拥有一个真实的领域内核（LinkML → pyoxigraph 知识图谱 + 40 余类实体 + 双向追溯边）、一条已代码化的阶段转换门禁链（`cataforge phase transition` 七门、exit 0/3 语义 + `--ack-*` 决策回传 + 审计落盘）、29 项与 CI 同源的静态守卫、约 3500 个测试、四平台能力矩阵与逐平台部署漂移检测。**框架元层（框架自身的正确性）成熟度高（3–4 级）；项目执行层（下游 LLM 开发的运行时约束）成熟度中等（1–3 级）**——恰好和它作为"方法学 Harness 而非 Agent Loop"的定位一致：静态可检查的都很硬，需要运行时执法的（任务级状态机、编码前侦察证明、Evidence Package、Feature Flag 生命周期）主要还靠 prompt 纪律。

对"能否支撑 LLM 主力完成中大型项目"的回答：**基本条件已具备，但有三类薄弱环节在中大型项目下会被放大**——(a) 任务级（相对阶段级）的状态与证据缺乏机器执法（本次已部分补齐）；(b) "宣称已验证"与"实际被执行"之间存在静默falsy空间（SHACL 三重失效是典型，本次已闭合）；(c) 失败恢复只有会话级重建（EVENT-LOG + §项目状态 + Recovery 协议），没有任务子图级局部恢复。

**与任务书"已知设计背景"的关键偏差**（以仓库事实为准）：

- 不存在 T0/T1/T2/T3/TA 命名分层；实际分层是 `interface → application → {runtime, domain} → adapter → core → utils`（`check_layer_dependencies.py` + import-linter 双守卫），语义上可映射（domain/kg ≈ Kernel、runtime+skills ≈ Domain Pack、hooks ≈ Sensor、doctor/checks/phase ≈ Gate、adapter/platform ≈ Adapter），但没有按能力域打包的机制。
- **不存在 "MCP → CLI → Manifest → Bare" 四档能力退化**；退化机制只覆盖 hook（native / rules_injection / prompt_instruction / prompt_checklist / skip，有测试）。
- **CataForge 自身没有 MCP server 表面**（`cataforge mcp` 仅管理外部 MCP 服务器）；"CLI/MCP 双表面"不成立，实际是 CLI 单表面。
- ID 体系不是 `<AREA>-<KIND>-<NUM>` 而是 `<PREFIX>-<NNN>`（30+ 前缀，per-class regex，从属实体 parent-scoped IRI）。
- **不存在子代理 → 顺序执行的运行时退化**；`execution_host: inline|subagent` 是部署期静态声明，交互性错配仅由 framework-review B5-ζ 静态审计拦截。
- `PROJECT-STATE.md` 是部署模板；活状态载体是部署后的 CLAUDE.md/AGENTS.md §项目状态（滚动窗口 + hygiene 门）+ `docs/EVENT-LOG.jsonl` + KG store。

---

## 2. 当前架构事实（凝练）

- **核心模块**：`domain/kg`（LinkML schema `core.yaml`/`governance.yaml` → codegen `core_pydantic.py`/`subclass_axioms.ttl`/`core_shapes.ttl`；facade / transaction（模拟事务 + 进程内锁）/ ingest 六阶段管线 / export 编译 / reconcile 三向哈希对账 / authority 五态漂移机 / trace 双向覆盖）；`runtime`（deploy 编排、agent 翻译、skill 执行、hook 桥接、mcp 生命周期、plugin）；`adapter/platform`（4 平台 profile.yaml + conformance + entry-point 扩展）；`application`（phase_transition 七门链、context 读写门、viz collectors）；`interface/cli`（20+ 命令组）。
- **工作流**：`framework.json#workflow` 为 SSOT（standard 7 阶段 / agile-lite 3 / agile-prototype 2，每阶段 role/output_doc_type/execution_host/interactive/skippable）；orchestrator 协议文档是只读视图。TDD 引擎四档（standard / light-dispatch / light-inline / prototype-inline），RED 阶段有行为断言强制表 + 假实现探测，GREEN 有 wiring_complete 自报 + 静态门 + 全量回归。
- **Gate 面**：`phase transition` 七门链；`doctor` 14+ 检查模块（含本次新增 SHACL conformance）；`run_local.py` 29 项静态守卫（=CI guards job）；doc-review / code-review / sprint-review 双层（Layer 1 脚本 + Layer 2 AI）；anti-rot 周扫；publish 门（tag=version=CHANGELOG）。
- **状态存储**：指令文件 §项目状态（orchestrator 独占写、单行超长 gating FAIL）+ `docs/EVENT-LOG.jsonl`（append-only，schema 校验）+ KG store（gitignored，快照恢复）+ `.cataforge/state/`（per-platform 部署记录、锁）。
- **测试与 CI**：3500+ 测试（e2e 真 wheel 安装、unattended 循环全出口路径、golden 导出哈希锁、平台隔离/共存/prune）；CI 三 job（guards / unit 矩阵 + 75% 覆盖门 / e2e）+ pr-title + anti-rot + no-dogfood-leak + publish。

---

## 3. 成熟度审查矩阵

评分：0 缺失 / 1 文档级 / 2 局部实现 / 3 强制执行 / 4 自验证。

| # | 维度 | 分 | 证据（代表性） | 结论 |
| --- | ------ | --- | ---------------- | ------ |
| 1 | 垂直切片 / Walking Skeleton | **3** | doc-review Layer 1 `_check_walking_skeleton`（arch 声明 `external_oracles` 而 dev-plan 无 `walking_skeleton: true` 卡 → FAIL）；`external-truth-first.md`；可选检查点 `post_skeleton` | 外部真值路径已是机检门；"每 Sprint 一条端到端切片"仍是 prompt 纪律（task-decomp/tech-lead），未上升为 Gate |
| 2 | Context Fit Gate | **1.5** | 任务卡 `context_load` 字段、`TASK_SPLIT_LOC=250`、AC>6 强拆（task-decomp SKILL）；无执行前的影响面/回归半径机器评估 | 拆分阈值是决案时约束；不存在进入 InProgress 前的 Context Fit 机检 |
| 3 | 编码前侦察 | **2**（替代设计） | `verified_anchors` 契约（SUB-AGent-PROTOCOLS §锚点传递）：主线程侦察并下发 file:line 锚点，子代理被要求**不**重复探索；重复实现靠 jscpd ≤1%（CI）+ implementer 自报 + sprint-review duplication 扫描事后兜底 | 与任务书方向相反但自洽：侦察责任在派发侧。"侦察确实发生"无证据要求，是缺口 |
| 4 | 可执行任务状态机 | 阶段 **4** / 任务 **1→3**（本次） | 阶段：`phase_transition.py` 七门 + `tests/cli/test_phase_transition_cmd.py`（非法转换/终态/ack 全覆盖）。任务：`TaskStatusEnum` 仅枚举，`update_entity` 原先零校验；**本次落地** `slot_guard` 转换表 + CLI `--ack-status-jump` + 测试 | 阶段级此前即达 4；任务级从 1 提至 3–4（graph 模式）。markdown 模式任务状态仍是文档行 |
| 5 | 任务依赖图与局部恢复 | **2** | dev-plan §2 mermaid + `task-dep-analysis`（拓扑/环检测）+ `sprint_groups` 并行派发；KG `depends_on` 边；unattended 循环有 stagnation 熔断/卡片修订上限 | 依赖表达完备；无失败类型/重试策略/证据失效传播/受影响子图重跑模型 |
| 6 | 接口成熟度与兼容性 | **1.5** | `ArtifactStatusEnum`（draft→…→superseded）+ 文档 approve 冻结（`guard_frozen_docs` hook 阻断编辑 + `ensure_document_replaceable` 拒绝 roundtrip 覆写 + ui-spec freeze gate）；代码级 API 无 Draft→Frozen 生命周期、无破坏性变更检测、无 contract test 框架要求 | 文档冻结真实存在且被 hook 强制；接口成熟度模型对**代码接口**缺位 |
| 7 | 分层外部记忆 | **3** | 不变层（rules 镜像注入）/ 慢变层（doc-index + `context read` 节级加载 + KG schema-context）/ Sprint 层（§项目状态滚动窗口 gating FAIL + EVENT-LOG）；`claude-md check/compact` 上限执法 | 三层记忆真实且有 hygiene 执法。缺：目录作用域局部规则（模块级 AGENTS.md）机制 |
| 8 | 能力注册表与重复实现防护 | **2** | KG Module/Component/API/Interface + `implements` 边即注册表（人工/LLM 经文档授权写入）；jscpd CI 门；orphan/xref/collision 检查 | 无代码符号↔KG 自动映射、无 Unregistered Capability 检查；注册表新鲜度依赖文档流程 |
| 9 | 依赖与外部 API 确定性 | **2.5** | 元仓：`uv lock --check` 入 run_local+CI（4 级）。下游：tech-eval skill、`arc-design` 包存在性核查、simulator 保真度契约、`guard_dangerous` hook；无 lockfile 强制门、无 Dependency ADR 机制 | 元仓自身 4 级；交付给下游的是 prompt 纪律 + hook，非 Gate |
| 10 | 验收 Oracle 与证据驱动 Done | **2.5** | `tdd_acceptance`（GWT，实现前定义，doc-review FAIL 缺失）+ RED 先失败测试 + sprint-review Layer 1（task_status_done / deliverables_exist / ac_coverage 机检）+ 保真度契约（placeholder 模拟器绿灯不作数）+ EVENT-LOG | Oracle 先行 + 完成三查是真实机制；但"测试真的跑过且通过"的证据是 agent 汇报 + orchestrator 复跑纪律，无结构化 Evidence Package 工件 |
| 11 | 风险分级与人工 Gate | **3** | `task_kind` × `security_sensitive` × `user_facing_critical_path` × `consumer_components` 驱动 per-task review 触发与 L2 跳过表（framework.json 常量）；检查点 pre_dev/post_sprint/pre_deploy + 可选 post_skeleton；`RiskLevelEnum` 在 schema | 事实上的 R0–R3 分级存在且驱动流程强度；未固化为单一 risk_level 字段 |
| 12 | 可逆变更与 Feature Flag 生命周期 | **0.5** | 框架自身 features 注册表有 min_version/auto_enable；对下游项目的 flag owner/默认态/删除条件/最迟清理期/关闭路径测试完全缺位 | 唯一接近 0 分的维度 |
| 13 | 执行器隔离与平台退化 | **2.5** | hook 四策略退化有测试；conformance 检查；per-platform manifest + 共享路径保护集 + 部署锁；`CATAFORGE_PLATFORM` 身份歧义显式失败 | 平台差异建模扎实；子代理顺序化退化机制不存在（静态审计兜底）；退化后语义等价无系统验证 |
| 14 | Gate 可执行性 | **3.5→4**（本次） | Schema/ID 唯一性/Orphan/Graph/xref/reconcile/phase 七门/claude-md/doctor 全部入 CLI+CI 且有测试；**审查发现的例外正是 SHACL**：shapes 被 gitignore 恒缺失、写路径从未传 `run_shacl=True`、真实管线产物本身不 conform（三处漂移）——"已验证"仅由玩具 shapes 桥接测试背书 | 本次将 SHACL 从"文档宣称"提至 4 级（提交+守卫+发布+conformance 回归+doctor 门+`--require-shacl`） |

---

## 4. 做得好的地方（为什么优于普通 Prompt 工作流）

1. **阶段转换已完成"散文状态机 → CLI 门禁链"的代码化**（0.18.0 `phase transition`）：漏步/顺序漂移风险从 LLM 注意力问题变成程序不变量；`--ack-*` 把"人类决策"显式建模为可审计输入而非提示词绕过。这是任务书优先级一要求的范式，框架已自行走到。
2. **KG-first 双模文档权威**：graph 模式下 markdown 是编译产物（golden 哈希锁定字节级），reconcile 三向哈希 + 五态漂移机 + 修复方向策略表把"文档 ↔ 图谱漂移"变成可枚举、可修复、入门禁的状态——这直接攻击 LLM 开发最大的跨会话失真源。
3. **守卫的元守卫**：`check_run_local_coverage` 强制每个确定性检查都接入 run_local（防"写了检查没接入主路径"），`check_prompt_cli_drift` 拦截 prompt 资产引用幻影 CLI 动词（防 prompt↔实现漂移），`check_ssot_reconciliation`/`check_schema_python_parity` 防跨资产双写。框架对"自身会腐化"有制度性自觉（anti-rot 周扫 + rot issue 自动开单）。
4. **验收纪律的对抗性设计**：RED 阶段的"假实现心智替换"检查、存在性断言禁止表、模拟器保真度契约（placeholder 绿灯不得作为通过证据）、`ENV-LIMITATION` 豁免禁令——这些是针对 LLM 具体失效模式（貌似通过、空接线、mock 自嗨）的精准反制，非通用软件工程搬运。
5. **平台层是真抽象非清单**：capability id → 平台工具名解析、hook 四策略降级产物化（生成 rules 文件而非静默丢弃）、per-platform 部署 manifest + drift 提示、换序部署字节稳定。
6. **无人值守循环工程化**：全出口路径（complete/stagnation/rate-limit/cap/preflight）有退出码级测试，静默存活监督、frozen-upstream preflight、每会话一卡约束——外循环不是脚本而是被测系统。

---

## 5. 薄弱点与根因

**A · 阻断中大型项目可靠运行**

- ~~SHACL 三重失效~~（已修，见 §7）。根因归类：DRIFTED + UNTESTED_DEGRADATION + BYPASSABLE——"生成产物非确定 → gitignore → 运行时恒跳过 → 跳过不失败 → 文档仍宣称已验证"是一条完整的静默失效链，每一环单看都合理。
- ~~任务槽零校验 + prompt 槽位漂移~~（已修，见 §7）。根因：数据结构能表达（枚举在 schema）但生命周期没有执行器；`check_prompt_cli_drift` 只查 CLI 动词不查槽名。
- Evidence Package 缺位（MISSING）：Done 的证据（命令、退出码、测试统计、时间戳）散落在 agent 汇报文本与 EVENT-LOG 事件里，无结构化工件、无 Gate 消费。中型项目多 Sprint 并行时无法审计"这个 done 凭什么"。
- 任务子图局部恢复缺位（MISSING）：失败后重入粒度是"会话重建 + 卡片重派"，无失败类型→受影响后继→选择性重跑模型。

**B · 跨会话漂移**

- markdown 模式任务状态是自由文本行，sprint-review 靠正则回填扫描（FRAGILE）；graph 模式本次已闭环。
- PRD 模板 P0/P1/P2 与 `PriorityEnum`（critical/high/medium/low）词汇双轨（DRIFTED，本次发现并记录，未改枚举——见 ADR 后果节）。
- `contains_entity` 此前对从属实体悬空（已修）——同类风险提示：xref 目标检查只覆盖 7 条追溯槽，结构边（has_section/part_of_document）无目标存在性检查（PARTIAL）。

**C · 降低开发效率**

- 编码前侦察无证据要求：verified_anchors 质量完全取决于主线程自律，锚点错误时子代理被明确要求"信任锚点"，错误会被放大（FRAGILE）。
- Context Fit 无机检：超上下文任务只能靠拆卡纪律事前防、靠失败事后发现。

**D · 体验/维护性**

- 子代理顺序化退化无机制（低能力平台直接声明 no，B5-ζ 静态拦截交互错配）——当前四平台都有原生派发，属前瞻债（UNTESTED_DEGRADATION）。
- 测试对环境 git 全局配置不设防（已修一例）。

**根因分布**：最大簇是"**生命周期没有执行器**"（任务状态、接口成熟度、flag 生命周期——枚举/字段在 schema，转换合法性无人执法），其次是"**Gate 未接入主路径**"（SHACL）与"**缺少自动化证据**"（侦察、Evidence Package）。架构模型本身（分层、KG、平台抽象）没有发现需要推翻的错误。

---

## 6. 目标架构与改进决策

层级归属采用现有分层的语义映射（不引入 T0–TA 重命名——OVERENGINEERED 风险大于收益）：

1. **Kernel（domain/kg + core）**：schema、枚举、状态机转换表、orphan/xref/collision/SHACL 校验、reconcile。任务状态机放这里（本次落地）——它是跨平台跨模式不变量。
2. **Domain Pack（.cataforge/skills + agents + framework.json workflow）**：TDD、review、decomp 等按职责的 prompt 资产；风险分级常量归 framework.json（项目可配置）。
3. **Sensor（runtime/hook + EVENT-LOG）**：证据采集面。未来 Evidence Package 的生产者应是 hook/CLI（PostToolUse 采集命令退出码），不是 agent 汇报。
4. **Gate（doctor + phase transition + run_local + CI）**：所有新 Gate 一律走"CLI 命令 + doctor 检查 + 测试"三件套，拒绝只存在于 skill prompt 的门。
5. **Adapter（adapter/platform）**：保持能力声明 + 降级产物化路线；子代理顺序化退化如实现，属 dispatcher skill + adapter 协作，不入 Kernel。
6. **项目配置（framework.json 用户块）**：检查点、阈值、风险策略、（未来）flag 策略。

一致性原则：任何"宣称能力"必须落在可执行表面（CLI/CI/doctor）+ 有失败测试，否则文档必须如实标注为纪律（prompt discipline）而非能力（enforced）。本次对 kg-verified-behaviors.md 的改写即按此执行。

关键 ADR：[adr-kg-write-guards-and-shacl-shipping.md](../architecture/adr-kg-write-guards-and-shacl-shipping.md)（SHACL 规范化发布路线、执法面三选、枚举内省事实源、状态机归属与 ack 模式）。

---

## 7. 已实施改进（本 PR）

每项均含目标 / 文件 / 验证 / 回滚。全量验证命令与结果见 §9 证据包。

1. **SHACL shapes 确定性化 + 提交 + 发布**
   - 文件：`scripts/codegen_kg_schema.py`（`_canonicalize_shacl`）、`.gitignore`、`scripts/checks/check_codegen_fresh.py`（GUARDED 3 artifacts）、新提交 `src/cataforge/domain/kg/_generated/core_shapes.ttl`
   - 验证：`tests/kg/test_codegen.py::test_shacl_shapes_byte_identical_on_rerun`；两次独立生成 cmp 相同（实测）
   - 回滚：还原 gitignore 行 + GUARDED 双元组 + 删除提交的 ttl
2. **schema ↔ 管线三处 conformance 漂移修复**
   - `core.yaml` Document 增 `content_hash` 槽（codegen 再生）；`_quads.py`/`ingest/writer.py`/`transaction.py` 的 `contains_entity` 经 `stored_entity_iri` / 事务内 staged 反查解析从属 IRI；`entity_extract.py` 增 AcceptanceCriteria `acceptance_text` 提取器
   - 验证：`tests/kg/test_shacl_conformance.py`（4 用例：双变体 conformance、悬空边归零、AC 必填槽）；golden 哈希不变（751 个 kg/context 测试全过，导出字节兼容）
   - 回滚：各文件独立可还原；schema 槽是加法变更
3. **`kg validate --require-shacl` + 结构化跳过原因 + doctor SHACL 门**
   - `validate.py`（`shacl_skip_reason`）、`interface/cli/kg/ingest.py`、`interface/cli/doctor/kg_ingestion.py`（`check_kg_shacl_conformance`，gating）、`doctor_cmd.py`
   - 验证：`tests/kg/test_cli_import_validate.py` 新增 3 用例（require 过/require 失败/普通 skip 仍提示不失败）；`tests/cli/test_doctor_kg_shacl.py` 4 用例（无店跳过/conform 过/违规 FAIL/缺依赖响亮降级）
   - 回滚：新 flag 与新检查独立删除，默认行为（`--shacl` note-only）未变
4. **KG 写入门槽守卫 + 任务状态机**
   - 新模块 `domain/kg/slot_guard.py`（枚举内省 `enum_values_for` + `TASK_STATUS_TRANSITIONS` + 两个 check 函数）；`transaction.py` add/update 接线（含 `_stored_class_name`/`_stored_literal`）；`application/context/write.py` 与 `interface/cli/context/write.py`、`interface/cli/kg/write.py` 的 `--ack-status-jump` 贯通与错误渲染
   - 验证：`tests/kg/test_slot_guard.py`（17 用例）+ `tests/context/test_task_lifecycle.py`（8 用例：完整生命周期、todo→done 拒绝且店不变、终态复活需 ack、创作期枚举拒绝、历史 `status=done` 漂移类硬失败、CLI 拒绝/放行）
   - 影响：越范围枚举值从静默写入变 exit 1（预期的行为收紧，ADR 后果节备案）
   - 回滚：slot_guard 模块 + 各接线点独立还原
5. **tdd-engine SKILL 槽位漂移修复**：`--slot status=done` → `--slot task_status=done`（`.cataforge/skills/tdd-engine/SKILL.md`）
6. **测试环境加固**：`tests/cli/test_git_cmd.py` 屏蔽 user/system git 配置（URL insteadOf 重写环境下 ensure-policy 误判）；`tests/context/test_write.py` 枚举合法化；`tests/kg/test_shacl_bridge.py` 适配新返回契约
7. **文档与记录**：ADR、`kg-verified-behaviors.md` SHACL 节按事实改写（含新执法面）、`cli.md`（新 flag/门/守卫语义）、changelog fragment `20260717_kg-write-guards-shacl-shipping.md`、本报告

裁定记录（事实 vs 文档冲突处置）：PR #512 changelog"写后跑 SHACL 校验"与实现不符——选择**修正文档口径 + 补足执法面**而非在写路径启用全量 SHACL（延迟与爆炸半径实测评估，见 ADR 方案比较）；写路径实际执行的 orphan/xref + 槽守卫在 kg-verified-behaviors.md 中如实表述。

---

## 8. 剩余差距 → 垂直改进 Sprint

按依赖与收益排序；风险 R1=单模块 / R2=跨模块或公开接口。

**S-1 · Evidence Package 最小闭环**（R2；前置：无）
结果目标：`cataforge evidence record`（命令、退出码、stdout 摘要、时间戳 → `.cataforge/state/evidence/` + EVENT-LOG 关联键）；sprint-review Layer 1 `task_status_done` 升级为"done 必须携带 evidence 引用，否则 FAIL"。涉及：interface/cli 新命令、sprint_review builtins、event-log schema 加法字段。验收：无 evidence 的 done 被 sprint-review FAIL 的失败测试；tdd-engine SKILL 收口步骤引用该命令。上下文范围：约 6 文件。

**S-2 · Context Fit 预检门**（R1；前置：无）
结果目标：`cataforge task fit <task-ref>`——从任务卡 `deliverables`/`context_load`/KG depends_on 计算涉及文件数、模块数、AC 数，对照 framework.json 可配置警戒线输出 pass/warn/fail 与超限原因；task-decomp 与 unattended preflight 接线。验收：超限卡产生结构化 fail 与拆分建议。约 4 文件。

**S-3 · 任务依赖图失败传播**（R2；前置：S-1）
结果目标：任务卡增 `retry_policy`/`failure_kind` 最小字段；`task-dep-analysis --impact <task-id>` 输出失败后失效的后继子集；unattended 循环按其只重派受影响卡。验收：模拟单卡失败仅重跑子图的集成测试。约 5 文件。

**S-4 · 代码接口成熟度**（R2；前置：无）
结果目标：`Interface`/`API` 实体的 `status` 复用 ArtifactStatusEnum 语义映射 Draft→Frozen；`kg trace` 增 frozen 接口消费者视图；doc-review/change-guard 对 frozen 接口关联实体的变更要求 ChangeRequest 实体。验收：frozen 接口无 CR 变更被 FAIL 的失败测试。约 6 文件。

**S-5 · Feature Flag 生命周期（下游）**（R1；前置：无）
结果目标：dev-plan 模板增 flag 声明块（owner/default/removal_condition/cleanup_by）；doc-review Layer 1 校验齐备性；sprint-review 对超期 flag WARN。纯模板+checker，无运行时。约 3 文件。

**S-6 · 结构边目标完整性 + priority 词汇统一**（R1；前置：无）
结果目标：`_check_xref_targets` 扩展到 has_section/part_of_document/contains_entity；PriorityEnum 与 P0/P1/P2 二选一统一（建议：模板改 MoSCoW→枚举映射表，或枚举改 P0–P2 并附 store 迁移说明）。约 3 文件。

未实施原因共性：S-1/S-3 需要新数据字段与跨子系统接线（本次审查约束"不一次性大重构"）；S-4/S-5 涉及下游模板契约变更，应走独立提案征求维护者对词汇/字段的决策；S-2 依赖对警戒线默认值的产品决策（任务书明确禁止把 30 文件写成绝对规则）。

---

## 9. Evidence Package

```yaml
audit_revision: 本 PR HEAD（见 git log）
repository_revision: b5013ed  # 审查基线（main）
reviewed_paths:
  - src/cataforge/{domain/kg,application,interface/cli,runtime,adapter,core}
  - .cataforge/{framework.json,skills,agents,rules,platforms,hooks,schemas}
  - tests/{kg,context,cli,deploy,platform,hook,e2e,unattended,golden}
  - .github/workflows/  · scripts/checks/  · docs/{architecture,reference,proposals}
commands_executed:
  - "uv sync --extra dev"                                    # exit 0
  - "uv run pytest -n auto --dist loadscope"                 # 基线: exit 1 → 1 failed(环境: git URL 重写)/3486 passed/13 skipped
  - "uv run --extra dev python scripts/codegen_kg_schema.py（两次独立输出 cmp）"  # exit 0, core_shapes.ttl 字节相同
  - "真实 shapes × 真实 ingest conformance 实验"              # 修复前: waterfall/agile 各 7 violations; 修复后: conforms=True
  - "uv run pytest tests/kg tests/context"                   # 751 passed
  - "uv run --extra dev python scripts/checks/run_local.py"  # exit 0, 29 checks passed（含 mypy --strict、codegen 3 artifacts）
  - "uv run pytest -n auto --dist loadscope"                 # 终态: 见下
tests_before: {passed: 3486, failed: 1(env), skipped: 13}
tests_after: {passed: "3520+（新增 32 用例）", failed: 0, skipped: 13}  # 终值以 PR CI 为准
implemented_changes: 见 §7（7 项，每项含回滚方式）
schema_changes:
  - "core.yaml: Document 类新增 content_hash 槽（加法，codegen 再生）"
gate_changes:
  - "kg validate: +--require-shacl, +shacl_skip_reason"
  - "doctor: +KG SHACL conformance（gating，缺依赖时响亮降级）"
  - "事务写入门: +枚举槽校验, +task_status 状态机(+--ack-status-jump)"
adapter_changes: 无（平台层未触碰）
generated_artifacts:
  - "src/cataforge/domain/kg/_generated/core_shapes.ttl（新提交，规范化，check_codegen_fresh 守卫）"
  - "src/cataforge/domain/kg/_generated/core_pydantic.py（再生：Document.content_hash）"
documentation_updates:
  - docs/architecture/adr-kg-write-guards-and-shacl-shipping.md（新）
  - docs/reference/kg-verified-behaviors.md（SHACL 节按事实改写）
  - docs/reference/cli.md（kg validate / kg update / context 写入门）
  - .cataforge/skills/tdd-engine/SKILL.md（槽位修正）
  - changelog.d/20260717_kg-write-guards-shacl-shipping.md（新）
  - 本报告
remaining_risks:
  - "下游存量 store 在 doctor SHACL 门下可能暴露历史违规（预期显性化；修复路径 re-ingest/repair）"
  - "枚举收紧对依赖静默写入越范围值的调用方是行为变更（changelog 已声明）"
  - "写路径未启用全量 SHACL（ADR 记录的延迟权衡）；orphan/xref+槽守卫覆盖主要腐化类"
human_review_required:
  - "S-6 priority 词汇统一方向（模板 vs 枚举）需维护者决策"
  - "S-1 Evidence Package 的 EVENT-LOG schema 字段命名需维护者确认"
```
