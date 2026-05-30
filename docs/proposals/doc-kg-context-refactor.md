# 上下文加载工具重构方案：doc 与 kg 的统一抽象层

> 范围：CataForge harness 工作流中两套"按需加载上下文"工具（基于 markdown 的 **doc** 工具 与基于知识图谱的 **kg** 工具）的职责澄清、统一抽象与配置驱动分发。
> 约束：只优化最终架构的清晰性 / 合理性 / 可扩展性，不计改造成本与向后兼容工作量。

---

## 1. 现状核实结论（含证据）

### 1.1 两套工具的真实形态

| 维度 | doc 工具 | kg 工具 |
|---|---|---|
| Skill | `doc-nav`（`.cataforge/skills/doc-nav/SKILL.md`） | `kg-ask`（`.cataforge/skills/kg-ask/SKILL.md`） |
| CLI | `cataforge docs load` / `docs index` / `docs validate` | `cataforge kg query` / `kg schema-context` / `kg import` / `kg reconcile` |
| 代码域 | `cataforge.domain.docs`（`loader.py` / `indexer.py` / `index_ops.py`） | `cataforge.domain.kg`（`facade.py` / `query.py` / `export/` / `ingest/`） |
| 读语义 | **按引用取章节**：`doc_id#§N[.ITEM]` → markdown 切片 | **按关系查图**：自然语言 → 只读 SPARQL → 追溯结果 |
| 写语义 | 无（生成走 `doc-gen`） | `kg add/update/delete`、`kg import`（由 doc-gen finalize 触发） |

### 1.2 关键事实：代码层"统一facade"已经存在

`cataforge docs load` 不是纯文件工具，它在 `loader.extract()` 内部已经做了 **per-doc_type 分发**：

- `src/cataforge/domain/docs/loader.py:239` — `extract()` 首先调用 `_try_kg_extract(...)`，命中则返回 KG 渲染结果，否则跌落到索引/文件切片。`plan_load`（`loader.py:315`）、`resolve_deps`（`loader.py:342`）同构。
- `src/cataforge/domain/docs/_loader_kg.py:42` — `_try_kg_extract` 用 `is_active_for(doc_id, project_root)` 决定是否走图；失败一律 `return None` 软降级到文件路径。
- `src/cataforge/domain/docs/_dispatch.py`（位于 kg 域，`domain/kg/_dispatch.py`）— `is_active_for()`/`active_doc_types()` 从 `framework.json` 的 `kg.kg_active_doc_types` + store 是否存在解析分发决策。
- `src/cataforge/domain/docs/kg_port.py` — 已用结构化 `Protocol`（`KGReadPort` / `KGQueryPort`）声明 docs 对 kg 的**只读消费面**，依赖方向单向（docs 拥有抽象，kg 结构化满足），这是教科书式的 DIP。

**结论 A**：在 read-by-ref 这条线上，doc 与 kg 的边界其实是干净的——kg 只是 `docs load` 的一个后端实现，由配置驱动分发。这部分架构是健康的，应作为统一抽象层的**蓝本**而非推翻对象。

### 1.3 问题 1（功能边界不清晰）——部分属实，根因在"关系/追溯"重叠

两套工具各自定义中都声明了"依赖/追溯"能力，导致**关系查询出现在两个读面**：

- `doc-nav/SKILL.md:13` 自称能力含"依赖链解析"，`doc-nav/SKILL.md:59`："依赖关系按 doc_type 分流：KG-active 走 `kg.query.depends_on` 图查询，legacy 走 `.doc-index.json` 的 `deps` 字段"。即 `docs load --with-deps` 本质是**一次图遍历**。
- `kg-ask/SKILL.md:3` 的定位是"针对项目知识图谱（需求/模块/任务/测试的**追溯关系**）检索"，举例"谁依赖 M-002"。

→ 同一类"实体间关系遍历"既能从 `doc-nav --with-deps` 进，又能从 `kg-ask` 进。**边界不清晰的真实位置不是"取章节 vs 查图"，而是"依赖展开"这一动作被切到了 doc 面，而它语义上属于图查询面。**

此外，`kg-ask` 是一个**孤儿读面**：它与 `doc-nav` 是平级 skill，但语料/职责描述里没有任何一处告诉调度方"取确定章节用 doc-nav，问关系用 kg-ask"——两者都笼统地宣称"按需加载上下文 / 避免读全文"，调用方缺乏选择依据。

### 1.4 问题 2（agent / skill 层调用方式重叠）——属实，根因是"分发决策"在 prompt 层被反复手写

代码层只有一处分发真源（`_dispatch.is_active_for`），但**该决策的自然语言版本被复制粘贴到至少 5 处 prompt 上下文**，每处都在重新解释"若 doc_type ∈ kg_active_doc_types 且 store 存在 → 走 SPARQL，否则 fallback"：

1. `doc-nav/SKILL.md:59` — 依赖分流叙述。
2. `.cataforge/rules/COMMON-RULES.md` §Agent 文档 I/O 契约 — "读取无需感知 KG 存在""依赖展开同样统一"等 5 条，整段在描述同一分发。
3. `doc-consistency/SKILL.md` — "KG dispatch（自动）：当 prd/arch/dev-plan ∈ kg_active_doc_types 且 store 存在时，AC 追踪检查改用 SPARQL……KG 不可达时自动 fallback"。
4. `doc-review/SKILL.md` — "Layer 1 KG 分流（自动）：doc_type ∈ kg_active_doc_types 且 store 存在时 `check_xref`→`query.exists()`、`check_bidirectional_coverage`→`trace.bidirectional_coverage()`；store 缺失自动降级"。
5. `task-dep-analysis/SKILL.md` — "KG 优先（dev-plan ∈ kg_active_doc_types 且 store 存在）/ Legacy 回退"。

调用面重叠的另一证据：**13 个 AGENT.md 全部声明 `doc-nav`，无一声明 `kg-ask`**（Explore 全量核对）。于是"读上下文"能力在 agent 视角是单一入口（doc-nav），但在 skill 实现视角又散落着各自的 KG 旁路——agent 不知道 kg-ask 存在，skill 各写各的分发。

**结论 B**：问题 2 的本质不是"两个工具都能干同一件事"，而是**统一抽象只做到了代码层 facade，没有上抬到 agent/skill 的 prompt 契约层**。分发是"实现细节"，却被泄露成每个 skill 文档都要复述的"调用知识"，长期必然腐化（与 CLAUDE.md 硬约束 1「最小可行修改」直接冲突）。

### 1.5 配置现状

- 唯一开关是 `kg.kg_active_doc_types`（`framework.json`，当前 6 个业务 doc_type 全开）。空数组 = 全部走 legacy（即"纯文档驱动"已可达，但无显式语义）。
- 默认即"KG 优先"——`KGConfig.kg_active_doc_types` 默认 = `BUSINESS_DOC_TYPES`（`domain/kg/_config.py:37`），再由 `is_active_for` 用 store 存在性兜底。
- **缺一个顶层语义开关**：现状用"逐 doc_type 的隐式集合"表达策略，没有 `kg-first | doc-only` 这样一眼可读的策略字段，下游要"纯文档驱动"得知道"把数组清空"这条隐式知识。

---

## 2. 目标架构设计

### 2.1 核心主张

把"按需取上下文"抽象成**一个读面（ContextProvider）+ 两个能力（resolve 取实体/章节、relate 查关系）**，分发隐藏在 provider 内部，对 agent/skill 只暴露**一套契约**。doc 与 kg 退化为 provider 的两个**后端实现**，由配置选择，互为降级。

### 2.2 分层示意

```
┌──────────────────────────────────────────────────────────────┐
│ Agent / Skill 层（prompt 上下文）                              │
│   只认一个能力契约： "Context I/O"                             │
│     · resolve(ref)        取确定实体/章节正文                  │
│     · relate(question)    查实体间关系/追溯                    │
│   不出现 "kg_active_doc_types / store 是否存在 / SPARQL" 字样  │
└───────────────┬──────────────────────────────────────────────┘
                │  单一 CLI 入口：cataforge context <verb>
┌───────────────▼──────────────────────────────────────────────┐
│ 统一抽象层  ContextProvider (interface/application)            │
│   resolve(ref) / relate(query) / plan(refs,budget) / deps(ref)│
│   —— 依据 ContextConfig.strategy + per-type 分发到后端 ——      │
└──────┬───────────────────────────────────────────┬───────────┘
       │ strategy=kg-first 且 type active 且 store 在 │ 否则
┌──────▼───────────────┐                   ┌─────────▼──────────┐
│ KgBackend            │                   │ DocBackend         │
│  domain/kg           │                   │  domain/docs       │
│  · render_entity     │                   │  · 章节切片         │
│  · query.* (SPARQL)  │                   │  · .doc-index.json │
│  · trace.*           │                   │  · deps[] 字段      │
└──────────────────────┘                   └────────────────────┘
        实现细节：经 KGReadPort Protocol 解耦（已存在）
```

### 2.3 与现状的差异（增量，不推翻）

| 现状 | 目标 |
|---|---|
| `loader.extract` 内联调用 `_try_kg_extract`，分发逻辑长在 docs 域里 | 分发上抬为独立的 `ContextProvider`；docs 与 kg 都成为它的后端，彼此不互相 import |
| `relate`（关系查询）能力分裂在 `docs load --with-deps`(图) 与 `kg-ask`(SPARQL) | `relate` 统一归到 provider 的关系能力；`--with-deps` 成为 `relate` 的一个预设 |
| `kg-ask` 与 `doc-nav` 平级、语义重叠、agent 只知前者 | 合并为单一 **`context`** skill（两个 verb），或保留两 skill 但由 provider 契约统一引用 |
| 每个 skill 文档手写一遍分发条件 | 分发只在 `ContextProvider` 一处声明；COMMON-RULES 仅一句"读上下文一律走 context 契约" |
| 策略=隐式的 `kg_active_doc_types` 集合 | 策略=显式 `context.strategy: kg-first \| doc-only`，doc_types 退为细粒度覆盖 |

---

## 3. doc 与 kg 的职责边界划分

划分原则：**doc = "文档作为载体（artifact-of-record）"，kg = "实体与关系作为事实（source-of-truth）"。** 二者不是两个平行的"读工具"，而是同一上下文的**两种投影**。

| 关注点 | 归属 | 理由 |
|---|---|---|
| 文件落盘形态、章节标题、行号、token 估算、`.doc-index.json` | **doc** | markdown 是人类可读/可 diff 的承载介质，索引是它的派生缓存 |
| 整段/whole-section 取正文（无实体语义的散文，如 `arch#§5` 概述） | **doc** | 图里没有"散文段落"实体，只能文件切片 |
| 实体（Feature/Module/Task/TestCase…）的规范化字段与渲染正文 | **kg**（经 `render_entity` 回投成 markdown） | 实体是事实主体；markdown 只是它的一个导出视图（`domain/kg/export`） |
| 实体间关系 / 追溯 / 覆盖 / 依赖（depends_on、satisfies、coverage…） | **kg** | 关系是图的一等公民；文件里只能用 regex 近似，易假阳/假阴（doc-consistency/doc-review 已据此切 SPARQL） |
| 自然语言关系问答（"哪些 Feature 没测试"） | **kg** | 需要图遍历，无文件等价 |
| 文档生成、评审、一致性校验的**载体侧**规则（结构、front matter、行数阈值） | **doc** | 作用对象是 markdown 文件本身 |
| 一致性/评审中的**关系侧**校验（xref 存在、双向覆盖、AC 追溯） | **kg** | 作用对象是实体关系 |

**边界判定一句话**：问题里出现"§N / 文件 / 整段正文" → doc.resolve；出现"谁/哪些/是否覆盖/依赖/追溯" → kg.relate。`--with-deps` 属于后者，应从 doc 面迁出。

---

## 4. 配置驱动的方案选择机制设计

### 4.1 顶层语义开关（新增 `context` 配置块）

```jsonc
// framework.json
"context": {
  "strategy": "kg-first",          // kg-first（默认） | doc-only
  "kg_active_doc_types": [          // 仅 kg-first 下生效：细粒度覆盖；
    "prd","arch","ui-spec",        // 省略=全部业务 doc_type；空数组=本类强制走 doc
    "dev-plan","test-report","deploy-spec"
  ],
  "fallback_to_doc": true           // store 缺失/损坏时是否软降级到 doc 后端
}
```

语义分层（从粗到细，下层覆盖上层）：

1. `strategy`（粗）：`kg-first` = 关系/实体能命中图就走图；`doc-only` = 完全旁路 kg，纯文档驱动（等价于今天清空数组，但显式可读）。
2. `kg_active_doc_types`（中）：在 `kg-first` 下精确指定哪些 doc_type 入图，用于滚动迁移。
3. `fallback_to_doc`（兜底）：保留 `is_active_for` 现有的"store 不存在即降级"语义，显式化为开关。

`doc-only` 下，provider 直接选 DocBackend，永不触碰 kg —— 这就是被明确保留的**纯文档驱动选项**，且默认相反（kg 优先），满足任务要求。

### 4.2 分发决策（单点，provider 内部）

```
resolve(ref):
    type = doc_type_of(ref)
    if strategy == kg-first and type in active and store_exists() and ref.is_entity:
        try: return KgBackend.render(ref)         # 实体级
        except: if fallback_to_doc: pass           # 软降级
    return DocBackend.slice(ref)                    # 章节级/散文

relate(query):                                      # 关系/追溯一律图；doc-only 下显式报"未启用"
    if strategy == doc-only: return DocBackend.deps_from_index(query)   # 仅 deps[] 近似
    return KgBackend.query(query)
```

要点：**这段决策只存在于 `ContextProvider`**。今天散落在 5 个 SKILL/RULES 的自然语言分发条件全部删除，由"调用 `cataforge context …`，分发对你透明"一句替代——直接消解问题 2，且贴合 CLAUDE.md「最小可行修改 / 解耦语言」硬约束。

### 4.3 可扩展性

新增第三种后端（如向量检索 `VectorBackend`）的改动闭合在三处：实现 `ContextBackend` 接口、在 `strategy` 枚举加值、在 provider 注册——agent/skill 与 5 个下游 skill **零改动**。这是把分发上抬为独立层的最大收益。

---

## 5. 分阶段、可执行的重构操作步骤

> 每阶段独立可合并、可回归。代码改动遵循 DDD 分层（domain 不依赖 interface）；prompt 改动遵循 CLAUDE.md 三条硬约束并跑 `python scripts/checks/run_local.py`。

### 阶段 0 · 固化契约（无行为变更）
1. 新建 `src/cataforge/application/context/provider.py`，定义 `ContextProvider` 与 `ContextBackend` 抽象（`resolve` / `relate` / `plan` / `deps`）。
2. 把 `domain/docs/kg_port.py` 的 `KGReadPort` 上移/复用为 backend 协议的基础，确认依赖方向：`application/context` → `domain/{docs,kg}`，两 domain 互不 import。
3. 为 provider 写契约测试（`tests/context/`）：同一 ref 在 kg-first+store 与 doc-only 两路径返回等价 markdown。

### 阶段 1 · 配置语义显式化
1. `core/config.py` + schema：新增 `context.strategy` / `context.fallback_to_doc`，并把 `kg.kg_active_doc_types` 迁移/别名到 `context.kg_active_doc_types`（`upgrade apply` 的 preserve 名单同步）。
2. `domain/kg/_dispatch.py` 改为读 `context.*`；`is_active_for` 增加 `strategy==doc-only` 短路。
3. `docs/reference/configuration.md` 增 `context` 块文档；标注 `doc-only` 即纯文档驱动、默认 `kg-first`。

### 阶段 2 · 收口分发到 provider
1. `domain/docs/loader.py` 的 `extract/plan_load/resolve_deps` 不再自行调 `_try_kg_*`；改由 `ContextProvider` 编排 DocBackend 与 KgBackend。`loader` 退化为纯 DocBackend。
2. `cataforge docs load` / `kg query` 两个 CLI 保留为薄入口，内部统一委派 provider；新增门面 `cataforge context resolve|relate|plan|deps` 作为首选入口。
3. 把"依赖展开"语义从 doc 面迁到 `relate`：`docs load --with-deps` 成为 `context relate --deps` 的兼容别名（或直接由 provider 路由）。

### 阶段 3 · 统一 agent/skill 调用面（prompt 层，最大清晰度收益）
1. 合并读面 skill：将 `doc-nav`（resolve）与 `kg-ask`（relate）整合为单一 **`context`** skill，含两个 verb 子能力；或保留两 skill 但都改为"`context` 契约的薄封装"。删去各自重复的能力边界叙述。
2. 删除分发复述：从 `doc-nav` / `doc-consistency` / `doc-review` / `task-dep-analysis` / COMMON-RULES 中删掉所有"doc_type ∈ kg_active_doc_types 且 store 存在 → SPARQL，否则 fallback"段落，替换为一句"读上下文走 `cataforge context …`，后端分发对调用方透明"。
3. AGENT.md 统一：13 个 agent 的 skills 列表把 `doc-nav` 替换为 `context`；产关系类校验的 agent（reviewer/qa-engineer/architect）显式获得 `relate` 能力，消除"agent 不知 kg-ask 存在"的裂缝。
4. 跑 `python scripts/checks/run_local.py`（design-residue / language-coupling / doc-structure 守卫）确保 prompt 文件合规。

### 阶段 4 · 清理与守卫
1. 删除 `domain/docs/_loader_kg.py` 中已上移的 `_try_kg_*`（其逻辑归 provider）。
2. 新增一致性守卫：禁止 SKILL/AGENT 主体再出现 `kg_active_doc_types` / `SPARQL` / `store 存在` 这类实现细节词（同 `check_no_language_coupling` 思路，把"分发知识"也纳入"不得泄露到 prompt 主体"）。
3. 在 `docs/architecture/runtime-workflow.md` 增"Context I/O 单一读面"小节，与本提案对齐；更新 `docs/reference/agents-and-skills.md` 的 doc-nav/kg-ask 条目。

### 阶段顺序与风险
- 0→1→2 是纯代码内聚，行为不变，可独立回归（契约测试护栏）。
- 阶段 3 是 prompt 大改但零运行时风险（skill 文档），收益最大（直接消解问题 1、2）。
- 阶段 4 收尾，把"不再泄露分发"用守卫固化，防止腐化复发。

---

## 附：现状证据索引（便于核对）

- 代码层已存在的统一 facade：`domain/docs/loader.py:239,315,342`、`domain/docs/_loader_kg.py:42`、`domain/docs/kg_port.py`、`domain/kg/_dispatch.py`。
- 关系能力重叠：`doc-nav/SKILL.md:13,59` vs `kg-ask/SKILL.md:3`。
- 分发被复述 5 处：`doc-nav/SKILL.md:59`、`COMMON-RULES.md §Agent 文档 I/O 契约`、`doc-consistency/SKILL.md`、`doc-review/SKILL.md`、`task-dep-analysis/SKILL.md`。
- 调用面裂缝：13/13 AGENT.md 声明 `doc-nav`，0/13 声明 `kg-ask`。
- 配置现状：`framework.json` `kg.kg_active_doc_types`（6 类全开）；`domain/kg/_config.py:37` 默认 KG 优先；无顶层 strategy 字段。
