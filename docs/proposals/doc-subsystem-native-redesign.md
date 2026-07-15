# 提案：文档子系统原生化重设计 —— 拆卷降为导出布局投影，kg-first 提示词全层对齐守卫锁死

> 状态：已实施。拆卷已彻底废除（一逻辑文档 = 一评审文件，超长文档仅精简不拆分）——相对本文「拆卷降为导出布局投影」的目标形态为已接受的实施偏离，导出布局投影未保留，勿再提议 split 导出或分卷；DomainEntity 逃生阀（前缀注册全链）与交叉引用纯 §-ref 校验均已落地。以代码为准，本文余下为历史设计记录。
> 范围：文档结构模型（图 `Document→Section` 权威 + 拆卷降级）、跨卷读契约、拆卷/合卷导出布局能力、Layer 1 与 doc_consistency 校验语义、6 产文档角色卡 Output Contract 与工具授权、context references 与新增语义守卫、双 mode 迁移；**本体对下游的扩展性与逃生通道**（`DomainEntity` 开放类 + 前缀注册，见 §1.5 / §3.8）
> 证据源：主线程直读源码核实（关键锚点在正文各处标 `file:line`）；四路 Explore 测绘（角色卡 I/O 契约、references+守卫、模板 registry、本体下游扩展逃生通道）
> 与既有提案的关系：延续 [`kg-first-authoring-inversion.md`](kg-first-authoring-inversion.md) 与 [`context-kg-subsystem-remediation.md`](context-kg-subsystem-remediation.md) 已落地原语（`ModePolicy`、`document_pipeline` 整篇导出器、三方哈希 drift triage、authoring API、`.nq` 快照）；**纠正**前者 P-1「按 `Document→Volume→Section` 树重建」的断言——`cf:Volume` 层从设计到落地一路被静默丢弃，是**死 schema**（详见 §1.1）；**不重开**已决项：不引第三种 `context.mode`、不恢复 `hybrid`、不把二进制 store 入库、不复活 `@requires_kg_first` 装饰器

---

## 0. 一句话

文档子系统的结构性腐化收敛到两条主题：**(1) 单一权威结构**、**(2) 静默数据丢失必须有信号 + 受控扩展点**。本提案把「拆卷」从一套会漂移的数据结构降为**图上单一逻辑 Document 的导出布局投影**（split 只在 finalize 发生，图/校验/读侧永远只见完整逻辑文档）；把「kg-first 反转」从只写在 references 层补齐到 6 个角色卡并新增**语义级守卫**断言该不变量；并给封闭本体开一个**有界的下游领域逃生阀**（`DomainEntity` + 前缀注册），把未知前缀的静默丢弃改为显式信号——使各类漂移与锁死结构上不可复发。四债诊断见 §1，收敛主题见 §1.6。

---

## 1. 根因诊断（直读源码核实，含对原始 framing 的三处纠正）

### 1.1 债 A — 拆卷：一套弱文件约定 + 一套死图 schema + 两后端各自把分卷当独立文档

「拆卷」当前在**三处**被建模，无一处是干净的单一权威：

| 建模处 | 内容 | 权威性 | 证据 |
|--------|------|--------|------|
| 文件 frontmatter | `split_from`（分卷→主卷 id）+ `volume`/`volume_type` | 文件层唯一实际归组信号，但**弱用** | 8 个 `role: volume` 模板，`_registry.yaml`；`id: prd-{project}-f{start}-f{end}` / `split_from: "prd-{project}"` |
| `.doc-index.json` | 每 doc 存 `split_from` 字段 | 被动投影（存而基本不查） | `_index_build.py:151,175` |
| 图 schema `cf:Volume` | `Document→has_volume→Volume→has_section→Section` + `part_of_volume` 全树 | **死 schema：声明却零生产者、零消费者** | 见下 |

**关键纠正 ①：图层 `cf:Volume` 树是死 schema，不是「与文件层并存的原生权威模型」。**

- ingest **从不创建** Volume 节点：`structure_extract.py:14` docstring 明写 *"split-Volume nodes are out of scope for this phase"*；`writer.py:285` docstring 明写只写 *"Document + Section structural nodes"*；`build_document_quads` 只接 `section_anchors`，无 volume 信息。
- export **从不消费** Volume：`document_pipeline._section_bodies` 只走 `cf:part_of_document`（Section→Document，`document_pipeline.py:101`），无 Volume traversal；`_list_documents` 逐 `cf:Document` 列举。
- grep 全 `domain/kg`（排除 `_generated`）：`Volume` / `has_volume` / `part_of_volume` 仅出现在 schema 声明、SHACL target 清单（`validate.py:61`）、注释——**零节点生产者、零节点消费者**。
- 连 `kg-first-authoring-inversion.md` P-1 自己写的「按 `Document→Volume→Section` 树重建」在落地时也悄悄退化为 `Section→Document` 直连。

**真实态**：每个分卷 .md（自带 frontmatter `id` 如 `arch-{project}-api`）经 ingest 成一个**独立 `cf:Document`**，图上无任何边把同一逻辑文档的分卷归为一组。文件层 `split_from` 是唯一实际记录「此文件是 X 的分卷」的地方，且只被 `doc_review` 反向 glob 消费。

**关键纠正 ②：主卷不持有分卷清单，跨卷 `doc#§N` 在两后端皆不透明。**

- 图读 `_loader_kg._kg_section_body`（`_loader_kg.py:85`）按 `cf:source_doc "{doc_id}"` **精确**匹配 Section——分卷 `source_doc = arch-{project}-api ≠ arch-{project}`，故 `arch#§3` 在图层命中空集。
- 文件读 `index_ops._resolve_doc_entry`（`index_ops.py:103-112`）用前缀 `{doc_id}-*` 兜底：单卷侥幸命中，**多卷抛 `AmbiguousRefError`**——无法知道 §3 落在哪个分卷。item 级 `arch#§3.API-005` 靠全局 `xref` 表跨卷解析（`index_ops.py:143`），但纯 section 级 `arch#§3` 无此救济。

**关键纠正 ③：拆分是纯人工，无任何 CLI/authoring 能力。**

- 全仓无 `split` 命令；`application/context` grep `split_from|volume_type` 零命中——authoring API（`write-doc`/`write`/`write-narrative`/`transact`）**完全无卷参数**（`context_cmd.py:269-300`）。
- 唯一「能力」是 `check_line_count`（`checker.py:185`）的 300 行 warning + generate.md:25 的手工「拆主卷+分卷」指令 + 8 个 volume 模板。拆分靠人手工造分卷文件、填 `split_from`。

**债 A 的结构性根因**：「一个逻辑文档可被切成多个物理卷」这个不变量**没有单一权威归属**——文件层记一半（`split_from`），图层声明了却不填（死 Volume），两后端实际都把分卷当独立文档。缺权威 → 跨卷解析必然靠 glob/前缀猜测 → 必然假阳性/歧义。

### 1.2 债 B — Layer 1 跨卷校验建立在弱结构上（含对「多卷误计」claim 的证伪）

| 检查 | 现状 | 缺陷 | 证据 |
|------|------|------|------|
| `check_xref` | 非 KG 走 `glob(doc_id*)` 只验**文件存在**、不验 §；KG 只验 entity ref（`[A-Z]+-\d{3,}`），纯 section ref 直接 `continue` 跳过 | 跨卷 `arch#§3` 找到某 `arch*` 文件即过关，从不验 §3 是否真在对应卷 | `checker.py:191-222` |
| `check_bidirectional_coverage` | 仅主卷跑（`volume_type != "main"` 直接 return）；非 KG 扫上游 `**/{up}*.md` 收 F/M，但只在**主卷 `self.content`** 内字符串匹配 | 下游覆盖分散在分卷时，主卷单卷匹配 → 假「未覆盖」 | `checker.py:337-386` |
| `check_split_consistency` | 主卷 glob `{stem}-*.md`，仅 warn 主卷是否文本提及分卷文件名 | 不验 `split_from` 指向的主卷是否存在、不验分卷 frontmatter 齐全——纯文本猜测 | `checker.py:568-580` |
| 多卷覆盖矩阵语义 | **从未定义**：分卷是否需各自声明覆盖无规约 | 语义空白 → 行为不可预期 | — |

**关键纠正 ④：doc_consistency 并非「多分卷被当独立文档误计 F/AC」。**`_read_all_content`（`_parse.py:53`）把某 doc_type 下**所有分卷文件拼接成一个 blob**，对 regex 覆盖检查其实是**卷容忍**的。真实脆弱点是 KG 路径用**模糊子串** `FILTER(CONTAINS(STR(?src), "prd"))`（`checker.py:129,136` 等）判归属——任何 `source_doc` 含 `"prd"` 子串即算命中，是脆弱的启发式而非精确逻辑成员判定。

**债 B 的结构性根因**：校验建立在「弱文件约定 + glob 猜测」而非权威结构上。债 A 一旦解决（跨卷解析有权威归属），债 B 的 glob 假阳性 / 主卷单卷盲区 / 模糊子串自然消除——B 是 A 的下游症状。

### 1.3 债 C — kg-first 反转未传导到 6 角色卡，无语义守卫锁死

**references 层已表达反转，角色卡层全体矛盾**：

- `generate.md:3`：*"图后端就绪时**图谱是事实源，`docs/` 由 `cataforge context finalize` 导出供人审，不直写后端、不 `Write`/`Edit` `docs/` 文件**"*；`review.md:21`：*"不 `Edit` `docs/` 导出文件——图后端就绪时 `docs/` 是图的只读导出视图，直接 Edit 会被 `context reconcile` 判为 human_edit 漂移"*。
- 6 个产文档 AGENT.md（product-manager / architect / ui-designer / tech-lead / qa-engineer / devops）**全体**：Output Contract 框定「必须产出 `{doc_type}.md`」，`tools` 含 `file_write` + `file_edit`，`allowed_paths` 含 `docs/{type}/`，**零提** authoring / finalize / kg-first / 导出视图。
- 更强反证：architect 的 Anti-Pattern 明写「禁止 Bash 执行除 `cataforge context read` 之外的任何命令」（`architect/AGENT.md:36`）——它**结构上无法**运行 `context write-doc`/`finalize`，只能 file_write 直写 md。

**唯一守卫纯语法级**：`check_prompt_cli_drift.py` 只拦幽灵命令名（CLI 未注册的动词）+ superseded `kg import/export`，扫 `agents/**/AGENT.md` 等但**覆盖不到「角色卡在 graph 语境框定写 markdown 文件」这类流向语义腐化**（子代理核实：无任何 `check_*.py` 断言 authoring 流向 / docs 写权限不变量）。

**orchestrator 层已对齐**（Phase Transition Step 6 用 `ModePolicy` remediation：`export`→finalize / `ingest`→回灌；inline-fix 走 `write-narrative`+`finalize`，`ORCHESTRATOR-PROTOCOLS.md:122,147`）——**债 C 缺口精确收敛在 6 角色卡 + 其 tools/allowed_paths + 缺失的语义守卫**，不在 orchestrator、不在 references。

**债 C 的结构性根因**：kg-first「docs 是导出视图、不直写」这个不变量落在 references 与 orchestrator，漏在角色卡；无守卫锁死 → 角色卡随迭代必然继续 md-first 表述。

### 1.4 债的同构性（为何一次系统重设计而非逐条打补丁）

三债同构：**跨层不变量部分落地 + 无守卫 → 必然重新漂移**。债 A 是「逻辑文档→物理卷」不变量在文件层/图层/两后端各记一半；债 C 是「docs 是只读导出视图」不变量在 references/orchestrator/角色卡各记一半；债 B 是债 A 的下游。逐条修（补一个 glob、改一句措辞）只会再攒下一轮漂移。目标不是补丁，是让文档子系统呈现**单一结构模型 + 由守卫强制的原生追溯**。

### 1.5 债 D — 本体对下游封闭、无逃生通道、未知前缀静默丢弃

本债是与 A/B/C **不同结构的另一根轴**（本体治理：封闭 vs 开放），因它与债 C 共享「静默数据丢失、无信号」的主题而并入本提案统一处置。

**本体定位（先厘清一个普遍误解）**：KG 本体（`core.yaml` LinkML，~40 个类）建模的是 **CataForge 自身的 SDLC 文档产物 + 追溯矩阵**（Feature/Module/API/Task/TestCase/Deployment，追溯边 `implements`/`satisfies`/`verifies`/`realizes`），**不是下游项目的业务领域**。电商项目的 `Order`/`Payment`、医疗项目的 `Patient` 不是图里的类——它们只以 `DataModel.field_definitions` 自由文本、`Glossary` 词条、Section `narrative_body` 散文形式存在。故本体在 **SDLC 工件层通用**（任何项目都有 Feature/Task/Test），在**领域建模层零通用**（它不是领域本体、也不自称是）。

**封闭且无逃生通道（直读核实）**：

| 事实 | 证据 |
|------|------|
| 本体是封闭打包 schema | `_schema_axioms.schema_paths()` 经 `importlib.resources` 只加载**打包内** `core.yaml`+`governance.yaml`，无用户路径覆盖；`ConfiguredBaseModel` `extra="forbid"`（`core_pydantic.py:42`） |
| 加类/加前缀/加 slot = 改框架源码 | 需编辑 `core.yaml` + regen pydantic + 更新 `iri.py:ENTITY_PREFIX_TO_CLASS` / `_config.py:ENTITY_CLASS_TO_DOC_TYPE` + 过 `check_codegen_fresh` 守卫 |
| `KGConfig.plugins_dir` 是死配置 | 全域 grep 无消费者（真实插件系统 `runtime/plugin/loader.py` 加载 skill/agent/hook/MCP，非本体） |
| config 旋钮只调路由/授权 | `kg_active_doc_types`（激活）、`kg_definition_authority`（扩已有类的权威 doc_type，只增不减）、`docs.doc_types`（映射）——无一能加类/前缀/slot（`_dispatch.py:78-107`） |
| `governance.yaml` 不是扩展点 | 固定的框架内治理子本体（skill/agent/rule 元数据），下游默认 `governance=false` |
| 无下游本体扩展文档 | `docs/reference/*` / `docs/architecture/*` 均无本体扩展段落；plugins.md 明写「插件扩展 skill/agent/hook/MCP，无需改本体」 |

**未知前缀在抽取层双重静默丢弃（本债最实的 wart）**：实体识别正则 `ENTITY_PREFIX_RE`（`entity_extract.py:106-109`）**由封闭前缀集派生**，`ORD-001` 根本不被识别为 entity-id；即便匹配，`:310` 也 `if class_name is None: continue`；关系抽取 `relation_extract.py` 对未知目标前缀同样 `continue`。下游领域概念**对图不可见、无报错、无警告**（doctor 仅当该 id 被 xref 引用时才判为 dangling，纯定义则零信号）。唯一「逃生阀」是自由文本 slot（`field_definitions`/`stack_layers`/`narrative_body`/`tags`）——opaque、不进追溯矩阵、不可 SPARQL 查询。

**债 D 的结构性根因**：本体被定位为封闭 SDLC 追溯脊椎（对该定位封闭是合理的：追溯矩阵良定义、前缀→类映射确定），但**缺一个有界的领域逃生阀**，且未知前缀**静默丢弃无信号**——使有新颖工件类型的下游除 fork 别无他路，且作者无从得知概念被吞。

### 1.6 债的收敛主题

四债收敛到两条主题：**(1) 单一权威结构**（A/B——拆卷单一建模、校验建于其上）；**(2) 静默数据丢失必须有信号 + 受控扩展点**（C/D——图与 md 双写的静默丢弃、未知前缀的静默丢弃，都要么锁死不变量、要么给一个带信号的逃生阀）。

---

## 2. 目标与原则

- **G1 单一结构模型**：拆卷只有一套权威建模。图 mode 下图是唯一事实源，物理卷是**导出布局投影**；文件层 `split_from`/`volume_type` 从「权威输入」降为「finalize 派生进导出文件的 frontmatter」，绝不回读为权威。
- **G2 拆卷原生化**：split 是 **finalize 时的布局决策**（由结构 + 每 doc_type 布局策略驱动），不是人工造文件；`doc#§N` 透明解析，调用方无需知 §N 落在哪个物理卷。
- **G3 校验建立在权威结构上**：Layer 1 跨卷检查走逻辑文档的严格解析（图 SPARQL / md 逻辑组索引），消除 glob 假阳性；多卷覆盖矩阵语义显式定义为「在逻辑文档全卷并集上计算」；split 一致性由结构不变量保证而非文本 glob。
- **G4 提示词资产全层对齐 + 守卫锁死**：6 角色卡 Output Contract 表达为两态（graph：authoring API 落图 + finalize 导出只读视图；markdown：直编 docs）；新增语义守卫断言「产文档角色卡不得在 graph 语境把写 `docs/*.md` 框定为交付物」，使债 C 类漂移结构上不可复发。
- **G5 双 mode 自洽**：`markdown`（无图）与 `graph`（图权威）两态下结构模型、读写契约、校验语义都自洽；降级路径明确（读侧 KG→file 保真回退已有；写侧 markdown mode 直编 docs 是合法态，角色卡显式区分）。
- **G6 下游本体逃生通道**：核心 40 类 SDLC 本体保持封闭（追溯矩阵良定义），新增**单一有界开放类 `DomainEntity`** + 下游前缀注册，让下游领域概念成为一等公民、可查询、可挂追溯边；未注册前缀由 doctor **显式 WARN**，消除静默丢弃。逃生阀有界（只一个开放类 + `domain_type` 判别符），不重开整本体给漂移。

**原则**：优先复用已落地原语（`document_pipeline` / authoring API / `ModePolicy` / reconcile triage / `.nq` 快照）；不为兼容旧结构保留重复包装/别名层，重构直接改测试指向新结构；窄 Protocol + 注入 > 引重型库；决策留可追溯记录（§7）。

---

## 3. 目标设计

### 3.1 统一结构模型：图 SSOT 持有单一逻辑 Document，拆卷是导出布局投影

**核心翻转**：graph mode 下，**一个逻辑文档 = 一个 `cf:Document`（id = 逻辑 doc_id，如 `arch-{project}`），持有其全部 Section（`part_of_document`）与全部实体，无论这些 Section 将被导出到哪个物理卷**。图上**没有**每卷独立 Document、**也没有 Volume 节点**——结构模型收敛为纯 `Document→Section`。

**`cf:Volume` 的去留（决议：删除死 schema，split 为导出侧纯函数，见 §7 决策 1 与落地计划 §A）**：深读 authoring/export 层（`author_document` / `compile_documents`）后定案——图本就是 `Document→Section`，Volume 从来不是数据；拆卷是 **finalize 时对 Document 全部 Section 的一个无状态分区函数**（按 `split_layout` 策略 + `VOLUME_OWNED_ID_PREFIXES` 计算 section→卷），**无需持久化任何 Volume 节点**。故 `cf:Volume` + `has_volume` + `part_of_volume` 死 schema **删除**（诚实移除，而非动画化一个平行结构节点——复活它等于重造债 A 的模式）。文件层 `split_from`/`volume_type` frontmatter 成为 finalize 从分区结果**派生**写进导出文件的投影，graph mode 永不回读为权威。

**跨卷 `arch#§N` 透明 by construction**：读侧/校验寻址**逻辑 Document**——`arch#§3` → 唯一 `arch` Document 的 Section §3。图上根本不存在「§3 在哪个卷」的问题，split 只在 export 出现。

**markdown mode（无图）**：物理卷文件即 SSOT，`split_from` frontmatter 是权威归组。修索引：构建 `logical_doc → [卷文件]` 组（替代 `_resolve_doc_entry` 反向 glob + 前缀歧义），跨卷 `arch#§3` 经组索引定位到拥有 §3 的物理卷，校验在并集上跑。**同一「逻辑文档」概念，归组键在 frontmatter 而非图边，由 `ModePolicy` 路由**（与其余一切 mode 相关行为同一分派点）。

**同一事实多处建模的权威性收敛对账**（重设计后）：

| 事实 | graph mode 权威 | markdown mode 权威 | 派生投影 |
|------|-----------------|--------------------|----------|
| 逻辑文档→物理卷归组 | `split_layout` 策略（config）对单 Document 的 Section 分区 | frontmatter `split_from` | 导出文件 frontmatter `split_from`/`volume_type`（graph 侧 finalize 派生） |
| Section→逻辑文档 | `cf:part_of_document` | 逻辑组索引 | — |
| 卷内容 | Document/Section narrative | 物理卷文件正文 | `docs/**` 导出视图 |

### 3.2 透明跨卷引用读契约

- `context read arch#§3` / `arch#§3.API-005`：解析器寻址**逻辑 doc_id**。graph → 查唯一 `arch` Document 的 Section；markdown → 经 `logical_doc` 组索引定位物理卷内 §3。调用方**永不点名物理卷**。
- **寻址形态收敛**：逻辑 doc_id + section 是唯一合法地址；`arch-{project}-api#§2`（卷 id 直接寻址）作为寻址形态**退役**——卷是物理/布局概念，不是寻址单元。这直接消除 `index_ops` 前缀歧义路径（`AmbiguousRefError` 的跨卷分支）。
- 降级不变：graph 读失败仍回退 file 后端（`_loader_kg` 的 `None`→file 契约保持）；两后端对同一 `arch#§3` 返回等价 markdown。

### 3.3 拆卷/合卷作为导出布局能力

- **split 是 finalize 时的每-doc_type 布局策略**：`docs.split_layout[doc_type] = { threshold, partition }`。`partition` 把 Section 确定性映射到卷。**分区规则的天然底座已存在**：`VOLUME_OWNED_ID_PREFIXES`（`constants.py:34`：features:{F,AC} api:{API} data:{E} modules:{M} sprint:{T} components:{UC} pages:{P}）—— Section 按其 `contains_entity` 的 ID 前缀落卷（如 API-* 段 → `arch-api` 卷）。无 owned 前缀的纯叙事段 → 主卷。
- finalize 据策略发 N 个文件：主卷含全局概览 + 交叉引用目录（派生自结构），分卷含各自 Section + 派生 `split_from`/`volume_type` frontmatter。**合卷 = 空 partition 策略（单文件）**。字节幂等由 `document_pipeline` 现有机制保证。
- **替代**：`check_line_count` 的 300 行 warning（超阈自动按策略拆，不再手工）、generate.md:25 的手工拆卷指令、8 个 volume 模板的人工实例化（模板降为布局策略的默认卷标题/必填章节来源）。

### 3.4 Layer 1 / doc_consistency 校验语义（权威结构上）

- `check_xref`：解析逻辑文档结构（图 SPARQL / md 组索引），验**文档存在 + §/entity 在逻辑文档内存在**。消除 glob 只验文件、跨卷盲区。真实不存在的纯 §-ref → fail（不再静默跳过）。
- `check_bidirectional_coverage`：在**逻辑文档全卷并集**上跑（图侧 `trace.bidirectional_coverage` 已全局、天然 OK；md 侧改为逻辑组并集，废除主卷单卷匹配 + `volume_type != "main"` 早退）。
- `check_split_consistency` → 降为结构不变量：graph mode 下 split 由布局策略确定性生成、finalize 是唯一写者，一致性 by construction；检查退化为「导出卷集合 == 布局策略分区 且 每卷 `split_from` == 逻辑 id」的结构相等，非文本 glob。md mode 验 `split_from` 指向存在的逻辑组 + 分卷 frontmatter 齐全。
- **多卷覆盖矩阵语义（显式定义）**：覆盖在逻辑文档全卷并集上计算；**单个分卷不各自声明覆盖**。写入 COMMON-RULES §Agent 文档 I/O 契约（填补「从未定义」空白）。
- doc_consistency：KG 路径的模糊 `CONTAINS "prd"` 换为**精确逻辑成员判定**（`source_doc ∈ 逻辑组`）；md 路径保留 blob 拼接但由逻辑组索引驱动（而非 `docs/{doc_type}*.md` 裸 glob）。

### 3.5 提示词资产全层对齐措辞（graph/markdown 两态）

6 角色卡 Output Contract 改为两态模板（措辞挂不变量，不让 agent 自行判 mode——`ModePolicy` 路由，参 COMMON-RULES §Agent 文档 I/O 契约「后端由框架路由，调用方不判断」）：

```
## Output Contract
- 交付物: {doc_type} 逻辑文档（拆卷由 finalize 按 docs.split_layout 布局，不手工造分卷文件）
- graph 后端就绪时: 经 `cataforge context write-doc`（整篇）或 `context write` / `write-narrative` /
  `transact`（增量）将 {doc_type} 落图；`docs/{doc_type}/` 是 `context finalize` 导出的只读审查视图，
  不 `Write`/`Edit` `docs/` 文件
- 无图后端(markdown mode)时: 经模板实例化后直接编辑 `docs/{doc_type}/`
```

- 同步修 architect 等卡的 Anti-Pattern「禁止 Bash 除 context read」→ 放行 `context write*` / `finalize` 授权动词。
- `tools` / `allowed_paths`：见 §7 决策 3——推荐**保留** `file_write`/`file_edit` + `docs/` 白名单（markdown mode 需要），由新守卫 + 两态措辞锁死 graph 语境不直写，而非靠工具清单裸剥夺（工具清单无法表达「仅 markdown mode 可写」）。

### 3.6 新增语义守卫规格（锁死债 C）

新守卫 `scripts/checks/check_doc_authoring_invariant.py`（接入 `run_local.py` + pre-commit + per-PR + anti-rot sweep；与 `check_prompt_cli_drift` 并列但语义级）：

- **扫描范围**：registry 声明的产文档角色 AGENT.md（product-manager / architect / ui-designer / tech-lead / qa-engineer / devops），及任何声明文档 Output Contract 的提示资产。
- **FAIL 判定**（流向语义级）：
  1. Output Contract 把交付物框定为**无条件**产出/写 `docs/*.md` 或 `{doc_type}.md`（命中「产出/写入 … .md」且**缺** `context finalize`/「导出视图」/「图后端就绪时」两态限定词）。
  2. 提示资产**无条件**指示 `Write`/`Edit` `docs/`（无 markdown-mode 限定）。
- **PASS**：Output Contract 用 §3.5 两态措辞。
- **RED-first 验证**：内置「md-first 角色卡」fixture 必须 FAIL、反转后 6 卡必须 PASS。
- **escape hatch**：同行 `<!-- allow-doc-authoring: <reason> -->`（依 repo 惯例）。

### 3.7 双 mode 自洽与降级

| 维度 | markdown mode | graph mode |
|------|---------------|------------|
| 结构权威 | 物理卷文件 + `split_from` frontmatter | 单一逻辑 `cf:Document`（纯 Document→Section，无 Volume 节点） |
| `arch#§3` 解析 | 逻辑组索引 → 物理卷 | 唯一 Document 的 Section |
| 拆卷 | 物理卷文件（`split_from` 权威） | finalize 按 `split_layout` 投影，图不含卷概念 |
| 校验 | 逻辑组并集上跑 | 图结构 SPARQL |
| 写侧 | 角色直编 `docs/`（合法态） | authoring API 落图 + finalize；不直编 |
| 降级 | 无图，file 后端唯一 | 读 KG 失败→file 回退；写不降级（图是唯一写入面） |

### 3.8 下游本体逃生通道：`DomainEntity` 开放类 + 前缀注册（债 D）

**设计原则**：核心 40 个 SDLC 类**保持封闭**（追溯矩阵、前缀→类映射的确定性是其价值）；开一个**有界的领域逃生阀**，而非把整本体改为可扩展（后者是 §7 决策 6 的 option 3，代价大、延后）。

**新增单一开放类 `cf:DomainEntity`（`is_a: SoftwareArtifact`）**——建模 SDLC 本体不覆盖的下游领域概念：

- `domain_type`（string, required）：下游自有类型名判别符（`"Order"` / `"Payment"` / `"Patient"`）。**可 SPARQL 查询**（`?e cf:domain_type "Order"`），这是它区别于自由文本 slot 的关键。
- `has_attribute` → `cf:DomainAttribute { attr_name, attr_value }`（结构化属性子节点，非 `key=value` 字符串）：领域属性**按名可查**（`?e cf:has_attribute [ cf:attr_name "amount" ; cf:attr_value ?v ]`）。选结构化子节点而非 opaque 字符串，正为满足「逃生阀不 opaque、可作为 typed 查询」（见 §7 决策 7）。
- 继承 `SoftwareArtifact` 的 `depends_on` / `part_of` / `located_in_section`，并可挂 `satisfies` / `implements`——**下游领域实体可接入 SDLC 追溯脊椎**（如某 `Order` 领域实体 `satisfies F-003`），这是逃生阀的核心价值：不是旁路存储，而是一等公民 + 可追溯。

**下游前缀注册（`framework.json`）**：

```json
{ "kg": { "custom_entity_prefixes": { "ORD": "Order", "PAY": "Payment" } } }
```

- 语义：自定义前缀 → `domain_type`。`ORD-001` 经 ingest 抽为 `DomainEntity{ domain_type: "Order" }`。
- **消除静默丢弃（债 D wart 的正解）**：实体识别前缀集从「硬编码 core 前缀」改为「core 前缀 ∪ 注册的 custom 前缀」；`ENTITY_PREFIX_TO_CLASS.get(prefix)` 对注册前缀回退 `DomainEntity`。**未注册**的未知前缀 → doctor `kg_ingestion_completeness` 显式 **WARN**（`ORD-001 出现但前缀未注册，将被丢弃——如需入图请在 kg.custom_entity_prefixes 注册`），不再零信号。
- **零 per-project regen**：`DomainEntity` + `DomainAttribute` 一次性加入 `core.yaml`（框架一次改动），下游经 config 注册前缀即用——**这是 option 2 相对 option 3（自定义 schema import）的关键优势**：`ENTITY_PREFIX_TO_CLASS`/识别正则只需变为 **config-aware**（core 静态前缀 + 运行时 custom 前缀集），不必把整个映射改为 schema 派生。
- **有界性保证不重开漂移**：core 其余 40 类仍封闭 + `extra="forbid"`；领域扩展全部收口在单一 `DomainEntity` + `domain_type` 判别符，无新 OWL 类/新 SHACL shape 逐类膨胀，追溯矩阵语义不被稀释。

**读/校验对齐**：`DomainEntity` 走与其它实体相同的 §3.1 结构模型（`located_in_section`→Section→Document）、§3.2 读契约、§3.4 校验；`context query` 的 schema card（`kg schema-context`）需纳入 `DomainEntity` + 项目已注册的 `domain_type` 清单，使 LLM 读到下游领域词汇。

---

## 4. 迁移与兼容路径

- **graph mode 存量（当前每卷独立 Document）**：一次性 remerge——复用 `scan → extract_{entities,relations,structure}` 管线重扫卷文件，按 `split_from`/逻辑 id 归组，把各分卷 Document 的 Section **归并到一个逻辑 Document**（section 的 `source_doc` 归一到逻辑 id），删旧的每卷独立 Document；`finalize` 按 `split_layout` 重发。幂等；`.nq` 快照（`snapshot.py:FINALIZE_SNAPSHOT_STEM="latest"`）为耐久底座、finalize 就地覆盖。
- **markdown mode 存量**：构建逻辑组索引（`_index_build` 增 `logical_doc` 归组），无图；`split_from` 保持权威 frontmatter。
- **framework.json**：新增 `docs.split_layout`（每 doc_type 布局策略），经 `_merge_framework_json` 补充、保留用户已配置值（不强制切 mode）；`features` / `migration_checks` 全量覆盖登记本次结构迁移检查。
- **doctor**：新增检查——graph：每逻辑 id 单一 Document、无孤立每卷 Document、导出卷集合 == `split_layout` 分区；md：`split_from` 指向可解析的逻辑组。
- **旧 `split_from` 分卷文件**：graph mode 迁移后成为 finalize 导出投影（不再权威输入）；md mode 保持原样。
- **退役**：`check_line_count` 拆卷 warning（能力落地后移除）；`cf:Volume` + `has_volume` + `part_of_volume` **死 schema 删除**（regen 同步）；`arch-{project}-api#§N` 卷 id 寻址形态（读契约收敛后 references/角色卡不再出现）。
- framework-walkthrough：双 mode（`graph` / `markdown`）各跑一遍拆卷路径，作为动态验收。
- **`DomainEntity` 逃生阀（债 D）纯增量、向后兼容**：`DomainEntity` + `DomainAttribute` 一次性加入 `core.yaml` 并 regen（`check_codegen_fresh` 同步）；存量项目不注册前缀则行为不变（core 40 类照旧）；`framework.json kg.custom_entity_prefixes` 经 `_merge_framework_json` 补充、保留用户值；识别前缀集改为 config-aware；doctor 新增未注册前缀 WARN。无存量数据迁移（旧项目本就没有 custom 前缀实体）。

## 5. 验收标准（真值门禁，非自报）

- **端到端（graph）**：一份大到触发拆分的文档，产文档角色**不经任何 `Edit docs/*.md`**、仅经 authoring API 产出；`context finalize` 按 `split_layout` 发 N 个卷文件；`context read arch#§N` 对**任意卷持有的 §N** 透明解析；Layer 1 `check_xref`/`coverage`/`split_consistency` 全绿；一条此前假阳性的跨卷 §-ref 现正确解析、一条真损坏 §-ref 现 fail。
- **端到端（markdown）**：同一拆分文档在无图项目下经逻辑组索引透明读、校验在并集上跑通。
- **守卫 RED-first**：`check_doc_authoring_invariant` 对 md-first fixture 卡 FAIL、对反转后 6 卡 PASS；先写失败测试（RED）再改角色卡（GREEN）。
- **结构不变量**：SPARQL 断言每逻辑 id 单一 Document、图中不存在 `cf:Volume` 类型节点、拆卷项目全部 Section `part_of_document` 指向同一逻辑 Document；`finalize → ingest → finalize` 字节幂等；waterfall/agile 两套 fixture 覆盖。
- **回归**：`run_local.py` 全绿（`check_prompt_cli_drift` + 新守卫 + ruff + 文档守卫 + `uv lock --check`）；全量 `uv run pytest -n auto --dist loadscope`。
- **双 mode walkthrough**：`graph` / `markdown` 各自 framework-walkthrough GO。
- **`DomainEntity` 逃生阀（债 D）**：注册 `kg.custom_entity_prefixes: {"ORD": "Order"}` 后，含 `ORD-001` 的文档经 ingest 产出 `DomainEntity{ domain_type: "Order" }`、`has_attribute` 结构化属性；SPARQL 按 `domain_type` 与 `attr_name` **可查**（断言渲染/查询后的可观测效果，非 slot 字面存在）；`ORD-001 satisfies F-003` 追溯边入图、`trace` 可达。**未注册前缀** `XYZ-001` → doctor `kg_ingestion_completeness` 产出 **WARN**（非静默、非零信号）。core 40 类回归零影响（不注册前缀时行为字节不变）。

## 6. 变更分解（依赖图 + 并行性）

四条轨，可独立验收；轨内按依赖排序，轨间标并行性。

- **轨-结构（图/读/导出）**
  - S1 图 SSOT 单一逻辑 Document + **删 `cf:Volume` 死 schema**（`core.yaml` 删类/slot + regen；`validate.py` SHACL target 去 Volume）
  - S2 读解析器逻辑文档透明（graph SPARQL 单 Document + md `logical_doc` 组索引；退役卷 id 寻址）— 依赖 S1
  - S3 导出布局能力（finalize 按 `split_layout` 对 Document 全 Section 无状态分区/合并 + 派生 frontmatter + 每输出文件 baseline）— 依赖 S1
- **轨-校验**
  - V1 `check_xref`/`coverage`/`split_consistency` 重写到逻辑结构 + 多卷覆盖语义定义 — 依赖 S1/S2
  - V2 doc_consistency 精确逻辑成员判定（去模糊子串）— 依赖 S2
- **轨-提示词+守卫**
  - P1 6 角色卡 Output Contract 两态措辞 + Anti-Pattern 放行 authoring 动词
  - P2 新语义守卫 `check_doc_authoring_invariant`（RED-first，可先于 P1 落）
- **轨-本体（债 D 逃生阀）**
  - O1 `DomainEntity` + `DomainAttribute` 加入 `core.yaml` + regen（`check_codegen_fresh`）
  - O2 识别前缀集 config-aware（core ∪ custom）+ `kg.custom_entity_prefixes` 注册 + 未知前缀 doctor WARN + schema-context 纳入 `domain_type` — 依赖 O1
- **轨-迁移**
  - M1 remerge 迁移 + doctor 检查 + framework.json `split_layout`（`_merge_framework_json`）— 依赖 S1
  - M2 双 mode framework-walkthrough 冒烟 — 依赖全轨

**并行性**：轨-提示词+守卫（P1/P2）⊥ 轨-结构（S1/S2/S3）⊥ 轨-本体（O1/O2）——三轨互不阻塞（本体逃生阀改 `core.yaml`/`iri.py`/doctor，与拆卷结构层解耦）；P2 可 RED-first 先落再驱动 P1。轨-校验依赖结构轨。轨-迁移 M1 依赖 S1。**优先级**：P2→P1（守卫锁死债 C）+ O1→O2（消未知前缀静默丢弃）+ S1（结构根因）三线并行起步；V*/M* 随 S* 就绪推进。

## 7. 关键决策记录

| # | 决策 | 选项 | 推荐 | 重评估触发 |
|---|------|------|------|-----------|
| 1 | `cf:Volume` 去留（**落地计划 §A 已改判**） | (a) 复活为布局节点 / (b) 删除，split 为导出侧对 Document 全 Section 的无状态分区函数 / (c) 删除，布局挂 Section `render_volume` 槽 | **(b)**（改判自初稿的 (a)）：深读 authoring/export 层后定案——Volume 从不是数据，分区可在 finalize 由 `split_layout` + `VOLUME_OWNED_ID_PREFIXES` 无状态算出，无需持久节点；复活 Volume 等于重造债 A 的平行结构节点；删死 schema 更诚实、更"单一结构模型"。per-file baseline 成本 (a)/(b) 相同，故 Volume 节点零收益 | 若出现无法由策略派生的任意手工分区需求（非前缀、非 size）→ 重评估 (c) 的 Section 级布局槽 |
| 2 | 拆卷寻址 | (a) 逻辑 id + § 唯一地址、退役卷 id / (b) 兼容卷 id 寻址 | **(a)**：卷是物理/布局概念、非寻址单元；消 `AmbiguousRefError` 根因 | 若存量下游大量硬编码卷 id ref → 加别名期迁移而非长期双形态 |
| 3 | 角色卡工具授权 | (a) 保留 file_write + docs/ 白名单，守卫+措辞锁死 / (b) 剥离 file_write、docs/ 只读 | **(a)**：markdown mode 需直写；工具清单无法表达「仅 md mode 可写」，语义守卫才能 | 若 markdown mode 被弃用 → 转 (b) 彻底剥离 |
| 4 | 拆分触发 | (a) 每 doc_type 显式 `split_layout` 策略（size 为默认分区）/ (b) 纯 size 阈值自动 | **(a)**：分区确定性、可复现（`VOLUME_OWNED_ID_PREFIXES` 为默认）；(b) 分区不稳定 | 若多数项目从不需按前缀分区 → 简化为 size-greedy 默认 |
| 5 | graph mode 是否仍保留物理拆卷 | (a) 默认单文件、`split_layout` 显式 opt-in / (b) 沿用阈值默认拆 | **(a)**：图从不需要卷、读从不加载整文件，拆卷纯人审/git-diff 工效；默认不拆最简 | 若人审强依赖分卷版式 → 提高默认拆分倾向 |
| 6 | 下游本体逃生阀深度 | (a) 前缀注册+丢弃信号 / (b) 开放 `DomainEntity` 类 / (c) 自定义 schema import | **(b)**（含 (a) 的丢弃信号）：给领域概念一等公民+可查询+可追溯，零 per-project regen；core 保持封闭；(c) 完全开放代价最大（去硬编码映射+per-project regen），下游需求证实前不做 | 若多个下游需要**逐类 SHACL 校验/OWL 推理**的领域本体 → 升 (c) 自定义 schema import |
| 7 | `DomainEntity` 领域属性形态 | (a) 结构化 `DomainAttribute{attr_name,attr_value}` 子节点 / (b) 多值 `key=value` 字符串 | **(a)**：属性按名 SPARQL 可查，满足「逃生阀不 opaque」；(b) 退回自由文本、不可 typed 查询（正是债 D 现有 wart） | 若属性从不需按名查询、仅供 LLM 散文消费 → 简化为 (b) |

---

**可执行分解**：逐轨的文件/函数/RED-first 测试/验收/依赖级落地计划，及 framework-review 静态核实结论，见配套 [`doc-subsystem-native-redesign-plan.md`](doc-subsystem-native-redesign-plan.md)。

**采纳前置**：本提案经 framework-review（元资产静态审，**已执行**，结论见 plan §A，verdict `approved_with_notes`）+ framework-walkthrough（双 mode 端到端动态自测，**留待各轨落地后**）双验；落地按 §6 轨划分为可独立验收变更，进度以 git 历史 / 本文件头部状态行为准。
