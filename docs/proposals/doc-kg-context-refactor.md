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

### 2.1 两条修正（回应早期 read-only / 对称后端假设的不足）

第一版把抽象设为"只读的 ContextProvider + doc/kg 两个对称后端 + 互为降级"。两点须修正：

- **修正 A · 抽象不止于"读"**：doc/kg 的二元不只出现在加载上下文，还贯穿**生成（doc-gen）、评审（doc-review）、一致性（doc-consistency）、索引/入图（index / ingest）**整条文档生命周期。统一层必须覆盖生命周期能力，否则 doc-gen / doc-review 仍要各自手写"该走 doc 还是 kg"——问题 2 只解决了读这一段。
- **修正 B · 后端不应被强制对称**：doc 与 kg 的能力**不必也无法对称**。把二者塞进一个"对称后端 + 谁缺谁兜底"的模具，会逼 doc 去补它做不好的关系查询、逼 kg 去当它不该当的编辑载体。正确做法是**承认非对称**：各自按能力边界做到最大化，由路由层按"操作级最佳保真后端"分发，而不是"首选后端 + 全量兜底"。

### 2.2 核心主张：生命周期能力端口 + 非对称后端 + 操作级最佳保真路由

抽象层不是单一读 provider，而是一组**能力端口（Capability Port）**，每个端口横跨生命周期一段职责，挂一到两个后端实现；每个后端对每个**操作**声明保真度 `native | degraded | unsupported`；路由层按 `context.strategy` + 能力注册表，为每个操作选**当前可用的最高保真后端**。

| 能力端口 | 操作（operation） | doc 后端 | kg 后端 | 谁是 native |
|---|---|---|---|---|
| `ReadPort` | resolve(实体)、slice(整段)、navigate(TOC)、status(文档态) | 文件切片 + `.doc-index.json` | `render_entity` / Section 渲染 / Document 导航 | 实体→kg；整段/导航→引入文档本体后亦 kg（见 §3.2） |
| `RelatePort` | relate(NL问答)、deps、coverage、trace | `deps[]` 近似（degraded） | SPARQL / `trace.*`（native） | **kg**（doc 仅退化近似） |
| `WritePort` | finalize(doc)：落盘 + 注册到检索基座 | 写 md + `docs index` | 写 md(载体) + `kg import` + `reconcile` | 载体 md 永远 doc；图投影 kg |
| `VerifyPort` | check_xref、bidirectional_coverage、ac_traceability（关系类）；structure、frontmatter、行数阈值（载体类） | 关系类 regex(degraded)；载体类 file(native) | 关系类 SPARQL(native)；载体类 unsupported | 关系类→kg；载体类→doc |

**这直接回答问题 1**：doc-gen / doc-review 等 skill **本身不做分发**，它们调用能力端口的具体操作，分发发生在**端口内、操作粒度**：

- `doc-gen` 调 `WritePort.finalize(doc)`。端口内部按配置决定：active → 写 md + `kg import` + `reconcile`；非 active / doc-only → 写 md + `docs index`。生成产物始终是 markdown（载体不变），"注册到哪种检索基座"是端口的事，skill 不感知。
- `doc-review` 调 `VerifyPort.check_xref()` / `check_bidirectional_coverage()`。每个 check 是一个操作：kg 能 native 服务（`query.exists` / `trace.bidirectional_coverage`）就走 SPARQL，否则走 file-glob。skill 只声明"我做评审，逐项交给 VerifyPort"，不再复述分发条件。
- `doc-consistency` 同构：AC 追溯是关系类操作（kg native），NFR/结构是载体类操作（doc native），端口分别路由。

### 2.3 分层示意

```
┌────────────────────────────────────────────────────────────────────┐
│ Agent / Skill 层（prompt 上下文）—— 按"职责"调用，不感知后端           │
│   doc-gen  → WritePort.finalize           doc-review → VerifyPort.*  │
│   doc-nav  → ReadPort.resolve/slice/nav    kg-ask    → RelatePort.*  │
│   不出现 "kg_active_doc_types / store 是否存在 / SPARQL" 字样          │
└───────────────┬────────────────────────────────────────────────────┘
                │   CLI 门面：cataforge context <port> <op>
┌───────────────▼────────────────────────────────────────────────────┐
│ 路由层 ContextRouter (application)                                   │
│   按 strategy + 能力注册表，为每个 op 选"最高保真且当前可用"的后端       │
│   规则：preferred=native → 用之；preferred≠native → 比保真度选；        │
│         preferred 不可用(store 缺) → 次优；全 unsupported → 显式报错     │
└──────┬──────────────────────────────────────────────┬───────────────┘
       │                                               │
┌──────▼──────────────────────────┐      ┌─────────────▼───────────────┐
│ KgBackend (domain/kg)           │      │ DocBackend (domain/docs)     │
│  Read : render_entity / Section │      │  Read : 章节切片 / TOC       │
│  Relate: query.* / trace.*      │      │  Relate: deps[]（degraded）  │
│  Write: ingest + reconcile      │      │  Write: 写 md + docs index   │
│  Verify: SPARQL 关系校验         │      │  Verify: file-glob 载体校验  │
│  本体含 Document/Section（§3.2） │      │  载体 = 人类可编辑 md 源     │
└─────────────────────────────────┘      └──────────────────────────────┘
        后端经 Port Protocol 解耦（已有 KGReadPort，按四端口扩展）
```

---

## 3. doc 与 kg 的职责边界划分（基于非对称能力，各自最大化）

### 3.1 划分原则

**doc = 人类可编辑的"载体源（source-of-record）"；kg = 机器可查询的"事实与关系基座（fact base）"。** 二者是同一上下文的两种投影，编辑发生在 md、查询发生在图，`ingest`/`reconcile` 维持两者一致。**不追求能力对称**——下表按"谁的能力边界天然覆盖该职责"归属，并标出各自应**最大化**的方向。

| 职责 | native 归属 | 另一侧能力 | 设计取向 |
|---|---|---|---|
| 人类编辑、git diff、字节/行级保真 | **doc** | kg 无（图是派生投影） | doc 保持唯一编辑入口 |
| 实体规范字段 + 渲染正文（F/M/T/TC…） | **kg** | doc 可文件切片但无字段语义 | kg 最大化：实体即一等公民 |
| 实体间关系 / 追溯 / 覆盖 / 依赖 | **kg** | doc 仅 `deps[]` 近似（degraded） | kg 最大化：图查询；doc 不强补 |
| 自然语言关系问答 | **kg** | doc 无等价 | kg 独占 |
| **整段散文 / 文档导航 / TOC / 文档态** | **kg（引入文档本体后）** | doc 文件切片仍可作 degraded 兜底 | **见 §3.2：把这块从 doc-only 升为 kg-native** |
| 载体类校验（结构、frontmatter、行数阈值） | **doc** | kg unsupported（作用对象是文件本身） | doc 最大化：守卫 md 形态 |
| 关系类校验（xref、双向覆盖、AC 追溯） | **kg** | doc regex 近似（易假阳/假阴，degraded） | kg 最大化：消除 regex 误判 |

### 3.2 让 kg 成为更完整的读后端：增加文档/章节本体（回应问题 2）

**现状证据**：`core.yaml` 里每个实体 `is_a SoftwareArtifact`，文档归属仅由两个**扁平字符串回指**承载——`source_doc`（line 168）、`source_section`（line 172）。**图里没有"文档"节点，也没有"章节"节点。** 这正是 `_try_kg_extract`（`_loader_kg.py:37`）对 whole-section ref（`item_id is None`）直接 `return None`、被迫回退文件的根因：图中没有可渲染的散文段落实体。结果 kg 结构上只是**部分读后端**，选了 kg 仍被拖回 doc API。`TechStack`（line 587）当年正是为"替换 tech-stack 的 `source_section()` escape hatch"才被建模成实体——已验证"散文转实体"路线，只是没推广到文档结构本身。

**修正**：在 `core.yaml` 增加文档结构本体，把回指字符串升级为真实图节点与边：

```yaml
Document:            # 一份业务文档（prd / arch / ui-spec / dev-plan / ...）
  is_a: SoftwareArtifact
  slots: [doc_type, title, status, has_part]   # has_part → Section / 业务实体
  # entity_id 形如 DOC-prd / DOC-arch；status 复用 ArtifactStatusEnum

DocumentVolume:      # 多卷文档的单卷（loader 已支持 doc_id-*.md 多文件）
  is_a: SoftwareArtifact
  slots: [part_of]   # part_of → Document

Section:             # 可按 §N 寻址的章节节点
  is_a: SoftwareArtifact
  slots: [section_anchor, heading_title, narrative_body, part_of, has_part]
  # part_of → Document/父 Section；has_part → 子 Section 或业务实体；
  # narrative_body 承载散文正文，content_hash 已存在用于 stale 检测
```

引入后 kg 读后端的能力扩张（操作从 doc-only 升为 kg-native）：

1. **整段读**：`prd#§5` 概述走 `Section.narrative_body`，不再强制回退文件——`ReadPort.slice` 在 active 下 kg-native。
2. **文档导航 / TOC**：`Document has_part Section` 直接图查询，取代 `.doc-index.json` 概览。
3. **文档态查询**：`Document.status` 可查（"哪些 arch 卷还是 draft"），文件侧只能扫 frontmatter。
4. **章节↔实体归属**：`Section has_part Feature` 让"§2 里有哪些 Feature""F-001 在哪一节"成为图查询；并把 `source_doc/section` 的扁平字符串升级为有引用完整性的边（`_entity_id_to_ref` 退化为一次图查找，`reconcile` 能检出孤儿章节）。

**留给 doc 的、不强行对称的部分**：markdown 作为人类编辑源与 git diff 对象、字节/行级保真。kg 是它的派生投影，编辑永远落在 md、由 ingest 回灌。于是非对称落到清晰边界：**kg native 于"检索/关系/导航"，doc native 于"编辑/载体保真"**，各自最大化，互不勉强。

### 3.3 边界判定一句话

出现"编辑 / diff / 文件形态 / 结构守卫" → doc；出现"实体 / 关系 / 追溯 / 导航 / 整段正文检索 / 文档态" → kg（active 下）。`--with-deps` 属关系类，迁出 doc 面归 `RelatePort`。

---

## 4. 配置驱动的方案选择机制设计

### 4.1 顶层语义开关（新增 `context` 配置块）

```jsonc
// framework.json
"context": {
  "strategy": "kg-first",          // kg-first（默认） | doc-only
  "kg_active_doc_types": [          // 仅 kg-first 下生效：细粒度滚动迁移；
    "prd","arch","ui-spec",        // 省略=全部业务 doc_type；空数组=本类强制 doc
    "dev-plan","test-report","deploy-spec"
  ],
  "fallback_to_doc": true           // 首选后端不可用(store 缺/损)时是否降级到次优后端
}
```

语义分层（粗→细，下层覆盖上层）：

1. `strategy`（粗）：`kg-first` = 凡 kg 能 native 服务的操作优先走 kg；`doc-only` = 完全旁路 kg，纯文档驱动（显式语义，取代"清空数组"的隐式知识）。
2. `kg_active_doc_types`（中）：`kg-first` 下精确指定哪些 doc_type 入图，支撑逐类滚动迁移。
3. `fallback_to_doc`（兜底）：首选后端对该操作不可用（store 缺失/损坏）时，是否退到次优后端。

`doc-only` 下路由层只挂 DocBackend，永不触碰 kg——这是被明确保留的**纯文档驱动选项**，且默认相反（kg 优先），满足任务要求。

### 4.2 路由决策（单点，operation 粒度，非"首选+全量兜底"）

```
route(port, op, args):
    candidates = backends_supporting(port, op)        # 查能力注册表
    if strategy == doc-only:        return DocBackend.run(op, args)   # 强制纯文档
    preferred = KgBackend if op_is_kg_preferred(op) else DocBackend
    if preferred.fidelity(op) == native and preferred.available(args):
        return preferred.run(op, args)
    # 非 native 或不可用：按保真度降序挑可用后端；fallback_to_doc 控制是否允许退 doc
    for b in sorted(candidates, key=fidelity, reverse=True):
        if b.available(args) and (b is not DocBackend or fallback_to_doc):
            return b.run(op, args)
    raise ContextUnsupported(port, op)                # 显式报错，不静默假装成功
```

要点：**所有分发只活在路由层**。今天散落在 5 个 SKILL/RULES 的自然语言分发条件全部删除，由"调用 `cataforge context …`，后端分发对你透明"一句替代——直接消解问题 2，贴合 CLAUDE.md「最小可行修改 / 解耦语言」硬约束。"非对称"在此显式化：某 op 只有一个后端能 native，路由就只有一个真实选项，不再假装两后端等价。

### 4.3 可扩展性

新增能力端口（如 `SummarizePort`）或新后端（如向量检索 `VectorBackend`）的改动闭合在：实现端口/后端接口、在能力注册表声明各 op 保真度、（新策略时）扩 `strategy` 枚举。agent/skill 与下游 skill **零改动**——这是把分发上抬为独立路由层、并按操作粒度声明能力的最大收益。

---

## 5. 分阶段、可执行的重构操作步骤

> 每阶段独立可合并、可回归。代码改动遵循 DDD 分层（domain 不依赖 interface）；prompt 改动遵循 CLAUDE.md 三条硬约束并跑 `python scripts/checks/run_local.py`。

### 阶段 0 · 固化端口契约（无行为变更）
1. 新建 `src/cataforge/application/context/`，定义四个能力端口（`ReadPort` / `RelatePort` / `WritePort` / `VerifyPort`）与 `ContextBackend` 接口（每 op 声明 `fidelity`），以及 `ContextRouter`。
2. 复用 `domain/docs/kg_port.py` 的 `KGReadPort` 作为 Read 端口协议基础，按四端口扩展；确认依赖方向 `application/context` → `domain/{docs,kg}`，两 domain 互不 import。
3. 为路由层写契约测试（`tests/context/`）：同一操作在 kg-first+store / doc-only 两路径行为符合能力声明（native 命中、degraded 降级、unsupported 显式报错）。

### 阶段 1 · 文档/章节本体落地（让 kg 成为完整读后端，回应问题 2）
1. `core.yaml` 增 `Document` / `DocumentVolume` / `Section` 类与 `doc_type` / `section_anchor` / `heading_title` 等 slot；重生成 Pydantic + OWL/SHACL。
2. `ingest/scan.py` 已产出 `HeadingSpan`（章节行范围）——扩 `ingest/` 把文档与章节也写入图（`part_of`/`has_part` 边），并把现有 `source_doc/source_section` 字符串回指升级为指向 `Document`/`Section` 的真实边。
3. `export/` 增 `Section` 渲染（`narrative_body` → markdown）与 `Document` 导航查询；新增 `section.sparql` 模板（无则走 `_artifact.sparql` 兜底）。

### 阶段 2 · 配置语义显式化
1. `core/config.py` + schema：新增 `context.strategy` / `context.fallback_to_doc`，把 `kg.kg_active_doc_types` 迁移/别名到 `context.kg_active_doc_types`（同步 `upgrade apply` preserve 名单）。
2. `domain/kg/_dispatch.py` 改读 `context.*`；`is_active_for` 增 `strategy==doc-only` 短路。
3. `docs/reference/configuration.md` 增 `context` 块文档；标注 `doc-only` 即纯文档驱动、默认 `kg-first`。

### 阶段 3 · 收口分发到路由层（覆盖读 + 生命周期）
1. **Read**：`domain/docs/loader.py` 的 `extract/plan_load/resolve_deps` 不再自调 `_try_kg_*`，退化为纯 DocBackend；whole-section 在 active 下改由 KgBackend 的 `Section` 渲染服务。
2. **Write**：`doc-gen finalize` 的"active→ingest+reconcile / 非active→docs index"分流，从 skill prose 迁入 `WritePort.finalize`。
3. **Verify**：`doc-review` / `doc-consistency` 内置 checker 的 KG 分流（`check_xref`→`query.exists`、`check_bidirectional_coverage`→`trace.*`、AC 追溯→SPARQL）迁入 `VerifyPort`，按 op 保真度路由。
4. **Relate**：`docs load --with-deps` 与 `kg-ask` 统一归 `RelatePort`；新增 CLI 门面 `cataforge context <port> <op>`，旧 `docs load` / `kg query` 保留为薄别名。

### 阶段 4 · 统一 agent/skill 调用面（prompt 层，最大清晰度收益）
1. skill 改为按"职责"声明端口调用：`doc-nav→ReadPort`、`kg-ask→RelatePort`（二者可合并为单一 `context` 读写门面 skill）、`doc-gen→WritePort`、`doc-review/doc-consistency→VerifyPort`。删去各自重复的能力边界与分发叙述。
2. 删除分发复述：从 `doc-nav` / `doc-consistency` / `doc-review` / `task-dep-analysis` / COMMON-RULES 删掉所有"doc_type ∈ kg_active_doc_types 且 store 存在 → SPARQL，否则 fallback"段落，替换为一句"走 `cataforge context …`，后端分发透明"。
3. AGENT.md 统一：13 个 agent 的 skills 列表把 `doc-nav` 替换为 `context`；产关系类校验/查询的 agent（reviewer/qa-engineer/architect）显式获得 `RelatePort` 能力，消除"agent 不知 kg-ask 存在"的裂缝。
4. 跑 `python scripts/checks/run_local.py`（design-residue / language-coupling / doc-structure）确保 prompt 文件合规。

### 阶段 5 · 清理与守卫
1. 删除 `domain/docs/_loader_kg.py` 中已上移的 `_try_kg_*`（逻辑归路由层）。
2. 新增守卫：禁止 SKILL/AGENT 主体出现 `kg_active_doc_types` / `SPARQL` / `store 存在` 等实现细节词（沿 `check_no_language_coupling` 思路，把"分发知识"纳入"不得泄露到 prompt 主体"）。
3. 更新 `docs/architecture/runtime-workflow.md`（增"Context 能力端口"小节）与 `docs/reference/agents-and-skills.md` 的 doc-nav/kg-ask 条目。

### 阶段顺序与风险
- 0→1→2→3 是代码内聚，行为等价或仅扩张 kg 覆盖面，可独立回归（契约测试 + 本体 round-trip 测试护栏）。
- 阶段 1（本体）是 kg 能力扩张的前置，须先于阶段 3 的 whole-section 收口。
- 阶段 4 是 prompt 大改但零运行时风险，收益最大（消解问题 1、2）。
- 阶段 5 收尾，用守卫固化"不再泄露分发"，防止腐化复发。

---

## 6. Skill 命名与分支重构（细化第 4 阶段，含完整 blast-radius 与依赖顺序）

第 4 阶段把"统一调用面"列为目标，本节给出可执行细则：把扁平的 `doc-nav` / `doc-gen` / `doc-review` / `doc-consistency` 四个 `doc-*` 同级 skill 收敛为**单一 `doc` 父 skill + reference 分支**，`kg-ask` 保留为独立的关系查询 skill。目的：让"doc-" 这个伪层级变成真正的父子结构，每个操作的详细 playbook 仅在该操作执行时按需进入上下文。

### 6.1 目标 skill 树（before → after）

```
before（5 个同级 skill，发现面 5 条 description）
  .cataforge/skills/doc-nav/SKILL.md
  .cataforge/skills/doc-gen/SKILL.md         + templates/
  .cataforge/skills/doc-review/SKILL.md      ⇄ builtins/doc_review/
  .cataforge/skills/doc-consistency/SKILL.md ⇄ builtins/doc_consistency/
  .cataforge/skills/kg-ask/SKILL.md

after（1 个父 skill + 1 个关系 skill，发现面 2 条 description）
  .cataforge/skills/doc/
    SKILL.md                  # 小调度体：生命周期图 + "按需 load 哪个 branch"
    references/
      navigate.md             # ← doc-nav 正文（ReadPort）
      generate.md             # ← doc-gen 正文（WritePort）
      review.md               # ← doc-review 正文（VerifyPort·单文档）
      consistency.md          # ← doc-consistency 正文（VerifyPort·跨文档）
    templates/                # ← 由 doc-gen 迁入
  .cataforge/skills/kg-ask/   # 保留：RelatePort，关系/追溯查询不属于文档生命周期
  src/cataforge/runtime/skill/builtins/doc/   # ← doc_review + doc_consistency 合并
    review.py                 # 入口（原 doc_review/doc_check.py 的 __main__）
    consistency.py            # 入口（原 doc_consistency/checker.py 的 __main__）
    checker.py / _checks.py / _render.py / typed_checks.py / constants.py / ...（helper 模块迁入）
```

运行时调用从 `cataforge skill run doc-review -- …` 变为 `cataforge skill run doc --script review -- …`（runner 的 `--script` 选择器，`runner.py:237` 已支持）。`_merge_builtin_fallback`（`loader.py:124`）会把项目级 `doc/SKILL.md`（无 scripts/）与 builtin `doc` 的 review/consistency 脚本合并，调用链不断。

**为何 `kg-ask` 不并入 `doc`**：它查询的是跨实体的事实基座（"哪些 Feature 无测试"），不是某一份文档的生命周期操作；并入会破坏第 3 节确立的非对称边界。保留为 RelatePort 的独立发现面。

### 6.2 运行时绑定改动（硬约束，必须同批落地）

| 文件:行 | 现状 | 改为 |
|---|---|---|
| `runtime/skill/loader.py:17` | `"doc_review": "doc-review"`（`_BUILTIN_ID_MAP`） | 删除该行；builtin 目录 `doc` 经 `_BUILTIN_ID_MAP.get(name, name)` 回退即得 id `doc` |
| `runtime/skill/loader.py:35` | `_BUILTIN_EVENT_LOGGED` 含 `"doc-review"` | 改为 `"doc"`（review/consistency 两脚本的 EVENT-LOG ref 已带 `skill:doc/<script>` 区分；consistency 由此也进入日志，为有意的可观测性增益） |
| `runtime/skill/builtins/doc_review/`、`doc_consistency/` | 两个独立 builtin 包 | 合并为 `builtins/doc/`：入口脚本 `review.py` / `consistency.py`（保留 `__main__` guard），helper 模块平移；修内部 import 前缀 `...builtins.doc_review`/`doc_consistency` → `...builtins.doc` |
| `runtime/skill/builtins/framework_review/checks/b3.py:75` | `"doc-review": "cataforge.runtime.skill.builtins.doc_review"` | `"doc": "cataforge.runtime.skill.builtins.doc"`（B3 按 skill-id 校验 builtin 模块路径） |
| `runtime/skill/builtins/framework_review/_constants.py:32,51` | `B1_REQUIRED_SECTIONS_EXEMPT_SKILLS` / `ORPHAN_SKILL_WHITELIST` 含 `"doc-nav"`、`"doc-gen"` | 改为 `"doc"`（父 skill 被各 agent 引用后，孤儿白名单项可同时移除多数条目） |
| `runtime/skill/builtins/doc_review/template_registry.py:40,49,99` | 硬编码 `.cataforge/skills/doc-gen/templates` | `.cataforge/skills/doc/templates`（模板随 generate 分支迁入 `doc/`） |

### 6.3 引用站点改动（breadth，按类别）

blast-radius 实测约 360 处、80+ 文件。按类别批改：

| 类别 | 量级 | 改法 |
|---|---|---|
| SKILL.md `depends:`（`loader.py` 解析） | 18 个依赖 `doc-nav`、7 个依赖 `doc-gen`、2 个依赖 doc-review/consistency 链 | 统一改为 `depends: [doc]`，去重（如 task-decomp `[doc-gen, doc-nav, task-dep-analysis]` → `[doc, task-dep-analysis]`） |
| AGENT.md `skills:` + 正文 | 10 agent 列 `doc-nav`、7 列 `doc-gen`、1 列 `doc-review`；正文 "通过 doc-nav/doc-gen…" | `skills:` 改 `doc`；正文 "通过 doc skill 的 navigate/generate/review 分支" |
| orchestrator / sub-agent / common-rules 协议 | Phase 2+ 触发、三审查 skill invocation、文档 I/O 契约 | `cataforge skill run doc-consistency -- docs/` → `... doc --script consistency -- docs/`；doc-review → `doc --script review`；doc-gen finalize → `doc` 的 generate 分支 |
| `framework.json` | `features.doc-review` 块；migration check 内 `.cataforge/skills/doc-gen/...` 路径（216/225/232/234）、shim 依赖（319）、kg-active 说明（327） | `features` key `doc-review` → `doc`（description 改为覆盖生命周期）；路径改 `.cataforge/skills/doc/...`；prose 引用改 `doc` |
| `docs/reference/agents-and-skills.md` | 5 行 skill 表 + agent 映射表 + 核心 skill 清单 + skill 卡片 | 重写为 `doc`（含 navigate/generate/review/consistency 子项）+ `kg-ask` 两条；agent 映射列 `doc` |
| 其他 docs | `cli.md:132`（事件日志清单 `doc-review`）、`status-codes.md:69`（doc-nav）、`README.md:46`（doc-review） | 文本替换为 `doc` |
| tests | `tests/skill/test_doc_review_*`、`test_doc_consistency*`、`tests/kg/test_doc_review_kg_dispatch.py`、`test_doc_consistency_kg.py`、`tests/e2e/test_docs_nav.py`、`tests/cli/test_doc_review_coverage.py`、`test_builtin_subprocess_contract.py` | import 前缀 `builtins.doc_review`/`doc_consistency` → `builtins.doc`；skill-run id `doc-review`/`doc-consistency` → `doc --script …` |
| CI | `.github/workflows/pr-title.yml:42` 示例 scope `doc-review` | 示例改 `doc`（仅注释性，非阻塞） |

**保留不改的**：常量名 `DOC_SPLIT_THRESHOLD_LINES` / `DOC_REVIEW_L2_SKIP_*`（`framework.json` + COMMON-RULES + checker + tests 多处引用，重命名是纯 churn、无澄清收益）；它们归属 `doc` 的 review 分支即可，名字不动。

### 6.4 依赖顺序与任务优先级（不可乱序）

按"被依赖者先行、改完即可独立回归"排序。S1 最高优先级（id 不解析则全链断）：

1. **S1 · 运行时绑定（foundation）** — §6.2 全部 + 同步改动到的 tests。先合并 builtin 包、改 loader/b3/template_registry，使 `cataforge skill run doc --script review|consistency` 端到端可跑。**Gate**：`pytest tests/skill tests/kg tests/cli/test_doc_review_coverage.py` 绿；`cataforge skill run doc --script review -- prd <doc>` 与 `--script consistency -- docs/` 返回码语义不变。
2. **S2 · prompt 树（structural）** — 建 `.cataforge/skills/doc/`：小调度 SKILL.md + 四个 `references/*.md`（迁入原四 skill 正文，同时按第 4 阶段删除其中 KG 分发叙述）+ `templates/` 迁入；删除旧 `doc-{nav,gen,review,consistency}/` 目录。**Gate**：`cataforge skill list` 含 `doc`、不含旧四 id；`cataforge deploy --dry-run` 复制 `doc/references/*`；framework-review B 系列检查通过。
3. **S3 · 引用 rewiring（breadth）** — §6.3 的 depends / AGENT / 协议 / framework.json。**Gate**：`cataforge doctor`（skill_health 无 dangling depends）；framework-review 孤儿/白名单检查通过；`python scripts/checks/run_local.py` 绿。
4. **S4 · 文档与 kg-ask 收尾** — 重写 `agents-and-skills.md` 分类、`cli.md` / `status-codes.md` / `README.md`；`kg-ask` 本体不变，仅同步引用文档。**Gate**：`cataforge docs validate` 干净。
5. **S5 · 守卫与清理** — 新增守卫禁止旧扁平 id（`doc-nav` / `doc-gen` / `doc-review` / `doc-consistency`）在 SKILL/AGENT/rules 主体复活；全量 `pytest` + `run_local.py`。

与前述端口/本体阶段的衔接：S1–S5 可独立于 `cataforge context` CLI（端口 CLI）落地；分支正文中"后端分发透明"的指向，待端口 CLI（前述第 3 阶段）就绪后由一次跟进 PR 把 `cataforge docs load`/`kg query` 替换为 `cataforge context …`。即本节先把 skill **形状**理清，端口 CLI 再把 skill 调用的**后端**理清，两者解耦推进。

### 6.5 关键实施细则

- **入口脚本识别**：`_scan_builtins`（`loader.py:179`）只把含 `if __name__ == "__main__"` 的 `*.py` 当作可运行脚本。合并后须确保 `review.py` / `consistency.py` 各保留 main guard，helper 模块（`checker.py` 等）不带 guard，否则会被误列为脚本、`--script` 默认错位。
- **default script 行为**：`runner._find_script` 在不传 `--script` 时取 `meta.scripts[0]`（按文件名排序）。合并后 `consistency.py` 排在 `review.py` 前，默认会落到 consistency。须在 `doc/SKILL.md` 与协议中明确两个 Layer 1 调用**始终显式带 `--script`**，避免依赖默认顺序。
- **EVENT-LOG 兼容**：`record_to_event_log` 现按 skill-id 生效；`doc` 入集后 review 与 consistency 都记录，ref 形如 `skill:doc/review`。reflector/sprint-review 若按旧 ref `skill:doc-review/...` 解析，需同步更新匹配前缀。
- **framework-review CHECKS_MANIFEST 对账**：`doc-review` 的 `CHECKS_MANIFEST`（COMMON-RULES 声明"与 manifest 不一致即 FAIL"）随包迁入 `builtins/doc/`，B3 模块路径同改；迁移后跑一次 framework-review 确认 manifest 对账通过。
- **deploy 无机制改动**：`deploy_skills` 按 skill 子目录整树 copy+render（`skills.py:110`），`doc/references/*` 与 `templates/` 自动随 `doc/` 部署，无需新增逻辑。

### 6.6 验证矩阵

| 验证项 | 命令 | 通过判据 |
|---|---|---|
| 运行时入口 | `cataforge skill run doc --script review -- <args>` / `--script consistency -- docs/` | 退出码与旧 `doc-review`/`doc-consistency` 一致 |
| 发现面 | `cataforge skill list` | 含 `doc`、`kg-ask`；无 `doc-nav/gen/review/consistency` |
| 依赖完整性 | `cataforge doctor` | skill_health 无 dangling `depends`；无 orphan 误报 |
| 元资产守卫 | `cataforge skill run framework-review` | B1/B3 + manifest 对账通过 |
| repo 守卫 | `python scripts/checks/run_local.py` | 11 项全绿 |
| 单测 | `pytest` | 全绿（重点 `tests/skill` `tests/kg`） |

### 6.7 风险与回滚

- **大面积重命名**：~360 处引用，遗漏即 dangling。缓解：S3 完成后用一次全仓 grep（旧四 id + `builtins.doc_review`/`doc_consistency`）断言零残留，并在 S5 落守卫固化。
- **默认 script 错位**：见 §6.5，靠"始终显式 `--script`"消除。
- **回滚单元**：S1–S5 各为独立可回滚提交；S1（runtime）与 S2（prompt 树）若需回退须成对回退，因二者共同决定 `doc` id 能否解析。

---

## 附：现状证据索引（便于核对）

- 代码层已存在的统一 facade：`domain/docs/loader.py:239,315,342`、`domain/docs/_loader_kg.py:42`、`domain/docs/kg_port.py`、`domain/kg/_dispatch.py`。
- 关系能力重叠：`doc-nav/SKILL.md:13,59` vs `kg-ask/SKILL.md:3`。
- 分发被复述 5 处：`doc-nav/SKILL.md:59`、`COMMON-RULES.md §Agent 文档 I/O 契约`、`doc-consistency/SKILL.md`、`doc-review/SKILL.md`、`task-dep-analysis/SKILL.md`。
- 调用面裂缝：13/13 AGENT.md 声明 `doc-nav`，0/13 声明 `kg-ask`。
- 配置现状：`framework.json` `kg.kg_active_doc_types`（6 类全开）；`domain/kg/_config.py:37` 默认 KG 优先；无顶层 strategy 字段。
- 本体缺文档/章节节点：`core.yaml` 全实体 `is_a SoftwareArtifact`，文档归属仅 `source_doc`（line 168）/ `source_section`（line 172）扁平字符串回指，无 `Document`/`Section` 类。
- kg 读后端结构性残缺：`_loader_kg.py:37` 对 whole-section（`item_id is None`）直接 `return None` 回退文件；`TechStack`（`core.yaml:587`）是已验证的"散文转实体替换 source_section escape hatch"先例。
