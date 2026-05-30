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

## 附：现状证据索引（便于核对）

- 代码层已存在的统一 facade：`domain/docs/loader.py:239,315,342`、`domain/docs/_loader_kg.py:42`、`domain/docs/kg_port.py`、`domain/kg/_dispatch.py`。
- 关系能力重叠：`doc-nav/SKILL.md:13,59` vs `kg-ask/SKILL.md:3`。
- 分发被复述 5 处：`doc-nav/SKILL.md:59`、`COMMON-RULES.md §Agent 文档 I/O 契约`、`doc-consistency/SKILL.md`、`doc-review/SKILL.md`、`task-dep-analysis/SKILL.md`。
- 调用面裂缝：13/13 AGENT.md 声明 `doc-nav`，0/13 声明 `kg-ask`。
- 配置现状：`framework.json` `kg.kg_active_doc_types`（6 类全开）；`domain/kg/_config.py:37` 默认 KG 优先；无顶层 strategy 字段。
- 本体缺文档/章节节点：`core.yaml` 全实体 `is_a SoftwareArtifact`，文档归属仅 `source_doc`（line 168）/ `source_section`（line 172）扁平字符串回指，无 `Document`/`Section` 类。
- kg 读后端结构性残缺：`_loader_kg.py:37` 对 whole-section（`item_id is None`）直接 `return None` 回退文件；`TechStack`（`core.yaml:587`）是已验证的"散文转实体替换 source_section escape hatch"先例。
