# Proposal: KG 从属实体 IRI 与定义判定根治（#210）

## 状态

**已实现** —— PR #219（修复 A · 定义判定收紧）+ PR #220（修复 B · 从属实体复合 IRI），随 v0.8.0 发布（breaking）。本文保留为设计记录；落地与原计划的差异见末节 [§实施修正](#实施修正)。

背景：`#210` 曾被 `#214`（`Closes #210`）关闭，但 `#214` 只把"跨文档同号实体静默塌缩"变成"`kg import` 检测到碰撞即 exit 3 中止"——一道**门禁**，把治理责任甩回文档侧，**没有触及 IRI 命名空间根因**。

下游 wechat-flow（`context.strategy=kg-first`，6 个业务 doc_type）在 0.7.0 开发版（HEAD `1a838c9`）上重新诊断，证明根因是**两个正交缺陷叠加**，纯文档治理对其中一类（从属实体）无解，故重开根治。

## 根因：双缺陷叠加

### 缺陷 ① 定义判定过宽（`entity_extract.extract_entities`）

抽取器把**任何非严格-xref、非 code-block 的裸 entity_id 出现**都当成一次"定义"，并以该出现所在 section 的整段 body 作 `content_hash`。

后果：一个实体在别处文档被**提及**（`relates_to: [F-001]`、行内 `（F-001 AC-004）`、任务卡标题里列的组件编号），都会被铸成那篇文档对该实体的"定义"，且 `content_hash` 取自不相干的宿主 section → 跨文档必然分歧 → 触发碰撞。

```python
# extract_entities：唯一的排除项是严格 xref 与 code block
xref_spans = [(m.start(), m.end()) for m in XREF_RE.finditer(doc.raw)]
for match in ENTITY_PREFIX_RE.finditer(doc.raw):
    if _inside_xref(match.start()): continue
    if _inside_code_block(match.start(), code_ranges): continue
    # ……其余一律当定义，hash 整个所属 section
```

### 缺陷 ② 从属实体用扁平全局 IRI（`iri.entity_iri`）

```python
def entity_iri(entity_id, base_namespace=DEFAULT_INSTANCE_NS):
    return f"{base_namespace.rstrip('/')}/{escape_iri_component(entity_id)}"
```

`AcceptanceCriteria`（`AC-NNN`）天然是**依附于父实体（Feature / Task / Component）的局部编号**：prd 的 `AC-001` 是 `F-001` 的第 1 条验收标准，dev-plan 的 `AC-001` 是 `T-001` 的第 1 条——**不是同一实体**。扁平 IRI `instance/AC-001` 把它们铸成同一节点。

更隐蔽：dev-plan 是分卷的，**每个任务卡 `T-xxx` 各有局部 `AC-001..AC-005`**。`extract_entities` 单文档内 `if entity_id in seen: continue` 让 dev-plan 内**几百个任务级 AC 也已被塌缩**（每个编号只留第一个）。→ 这决定了 scoping 不能按 doc，必须按 parent（见 D1）。

> `section_iri` 已有路径分段先例 `{base}/doc/{doc_id}/sec/{anchor}`，从属实体复合 IRI 仿此即可，非无先例设计。

## 诊断数据（wechat-flow 验证场景）

`kg import --dry-run --backend memory`（不写盘）：

| 指标 | 值 |
|------|----|
| entity 出现总数 | 911 |
| distinct entity_id | 227 |
| **碰撞 entity_id** | **76** → exit 3 中止 |

按"该 id 是否出现在其所属 section 标题里"（`title_defines` 启发式）对 76 个碰撞分类：

| 类别 | 数量 | 含义 |
|------|------|------|
| `pollution_only` | 33 | 1 个真定义（标题含 id）+ 其余文档纯提及 → 缺陷① |
| `no_owner` | 33 | 所有文档都只是提及，无人在标题定义 → 缺陷①（含全部 AC-001~012 = 缺陷②） |
| `genuine_multi` | 10 | ≥2 文档标题都含 id（实为 dev-plan 任务卡标题列了组件编号，如 `T-097: [DESIGN] Penpot — C-001/C-002/...`）→ 缺陷① |

每文档"被归属实体 / 其中提及污染"：arch 83/47 · dev-plan 191/45 · ui-spec 59/47 · prd 32/22 ≈ **161 处提及污染**。

代表样例：

```
### F-002   （真定义只在 prd）
    [ment] arch     L304  E-008: DiagnosticReport        ← 宿主 section 不相干
    [ment] dev-plan L115  T-006: packages/core 渲染管线骨架
    [DEF ] prd      L63   F-002: 视觉一致性与预览          ← 唯一真定义
    [ment] ui-spec  L27   C-001: 顶栏（TopBar）

### AC-001   （从属实体，缺陷②；各文档是不同父实体下的不同 AC）
    [ment] dev-plan L26   T-001: Monorepo 骨架初始化      ← T-001 的 AC-001
    [ment] prd      L22   F-001: 写作体验                ← F-001 的 AC-001
    [ment] ui-spec  L84   C-003: 工具栏按钮              ← C-003 的 AC-001
```

复现脚本见同目录 [`repro_diag.py`](./repro_diag.py)。

## 修复架构：两个正交改动

### A. 定义判定收紧（标题锚定）

普通实体（`F/M/C/API/P/E/T/...`）**仅当 entity_id 出现在其所属 section 的标题里**才算"定义"；其余裸出现不再铸实体。

- 提及若为严格 xref 形式 → 经 `relation_extract` 成边（`PREDICATE_MAP` 已支持 `cf:implements/satisfies/realizes/verifies`）。
- 消除 `pollution_only` + `genuine_multi` + `no_owner` 中的普通实体污染。

### B. 从属实体复合 IRI（by-parent）

从属类（`AcceptanceCriteria`，可扩展）改用 `{base}/instance/{parent_id}/{entity_id}`；父实体从 AC 所在 section 的 owning entity 解析（prd 的 AC 在 `F-001` 节 → parent=`F-001`；dev-plan 的 AC 在 `T-001` 节 → parent=`T-001`）。

- 取消从属类的 `seen` 单文档去重（改为 `(parent, entity_id)` 去重），保住任务级局部 AC。
- 消除 `no_owner` 中的 AC 塌缩。

## 关键决策

### D1 从属实体 scoping 维度 = **by-parent**（推荐）

| 方案 | IRI | xref 解析 | dev-plan 任务级局部 AC | 结论 |
|------|-----|----------|----------------------|------|
| by-doc | `instance/{doc_id}/{ac}` | xref 自带 doc，直接 | **仍塌缩**（doc 内多任务卡共用 AC-001） | ✗ |
| by-section | `instance/{doc_id}/{anchor}/{ac}` | xref 自带 §N，直接 | 保住 | 可行但 IRI 绑定 section 位置，重排即变 |
| **by-parent** | `instance/{parent_id}/{ac}` | xref 缺 parent，需从 §N 的 owning entity 解析 | **保住** | **✓ 语义正确，唯一兼顾** |

by-doc 被 dev-plan 分卷任务级局部 AC 直接否决。by-parent 语义最正（AC 属于某 F/T/C），代价是 xref 指向 AC 时需解析 parent（从 xref 的 `§N` 定位 owning section 的实体）。

### D2 `reconcile` 比对维度联动改造

现状 `reconcile` 按裸 `cf:entity_id` 字面量比对（`SELECT DISTINCT ?entity_id`），按 `cf:source_doc` 归属 doc_type —— 这正是 `#214` 描述的"repair 翻转 source_doc 打地鼠、`COUNT(DISTINCT ?s)` 永不收敛"。随 D1，比对 key 改为 `(scope_key, entity_id)`（普通实体 scope_key 空，从属实体为 parent_id），与 IRI scheme 对齐方能收敛到 0。

### D3 裸提及处理 = 忽略 + reconcile 报覆盖缺口（推荐）

定义判定收紧后，非 xref 的裸提及不再铸实体也不成边。温和降级（信息不全，由 reconcile 暴露覆盖缺口）优于现状的 import 整体 abort。可选后续：doc-review 增"裸 id 引用应改 xref"提示。

### D4 向后兼容 = breaking + minor bump

IRI scheme 变更使既有快照失效。需 minor 版本 bump + CHANGELOG 标 breaking + 下游 `kg init && import` 重导。wechat-flow 当前无 store（已删），无迁移负担。

## 全链路改面清单

| 模块 | 改动 |
|------|------|
| `entity_extract.py` | 定义判定收紧（标题锚定）；从属类识别 + parent 解析；从属类去重 key 改 `(parent, id)` |
| `iri.py` | 新增从属实体复合 IRI 函数；从属类声明 |
| `writer.py` | `write_entities` 按类选 IRI；relation subject/object IRI 解析支持从属类 |
| `relation_extract.py` | xref 指向从属类时从 `§N` owning section 解析 parent → 正确 IRI |
| `reconcile.py` | 比对维度 → `(scope_key, entity_id)` 复合 |
| `repair.py` | 随 reconcile 维度适配 |
| `verify.py` | `verify_after_write` 的 entity_count / hash 比对适配复合 IRI |
| `migrate.py` | `detect_entity_id_collisions`：从属类不再算碰撞；定义收紧后普通实体也不再碰撞 |
| `doctor`（kg_ingestion） | 复用 detect；written-vs-parsed delta 对账（#210 fix direction 2）|
| `structure_extract.py` | 实体挂 section 适配从属类 |
| `core.yaml` | 声明 subordinate classes 及其 scoping（schema 已有 `part_of`/`belongs_to_*` 槽可表达父子）|
| `export.py` / `compare_read.py` | IRI 变更适配 |
| tests | 381 KG 测试回归 + 新增"跨 doc_type 同号 + 任务级局部 AC"回归（#210 fix direction 3）|

## 验证闭环

1. wechat-flow `kg import --dry-run` 碰撞归零
2. `kg init && kg import` 实体数 ≈ markdown 解析数（不再 227 vs ~592）
3. `kg reconcile` 收敛到 0
4. `kg snapshot` + 提交 `.nq`
5. 全 KG 测试绿 + `run_local.py` 守卫通过

## 实施修正

落地（PR #219 + #220）相对本文原计划的差异，来自实施前对照代码的核实：

- **改面清单补漏 query / trace**：原清单缺 `query.py`（`entity/exists/depends_on/_fetch_typed`）与 `trace.py`（`coverage/from_requirement`）两个读侧 facade，它们按裸 id 重构扁平 IRI，从属实体复合后会查空。实现新增 `_sparql_utils.resolve_stored_entity_iri`——扁平 IRI 不存在时回退按 `cf:entity_id` 字面量解析实际节点；两 facade 改用之。
- **transaction.py 未纳入**：写侧手工 CRUD facade（`cataforge kg add/update`），ingest 不经它；保持扁平默认（`add_entity` 等未加 `parent_id` 形参），手工写从属实体属边缘场景，留待需要时扩展。
- **D2 reconcile 收敛实现**：未改 reconcile 的 SPARQL JOIN 维度，而是 FS/KG 两侧统一改用 scope key（普通实体 = `entity_id`，从属实体 = `parent/entity_id`，KG 侧经 `cf:part_of` 复原 parent）。关系对账仍按裸 id——关系边经 writer 解析指向复合节点后，`?o cf:entity_id ?o_id` 自然匹配。
- **父链用 `cf:part_of` 对象边**：复用既有 slot（AC `part_of` 其 Feature/Task），但它会被通用关系查询误判为 traceability 边，故在 reconcile 显式排除（仿 `cf:belongs_to_project`）。`SUBORDINATE_CLASSES` 单一事实来源置于 `iri.py`（与 `ENTITY_PREFIX_TO_CLASS` 同源），未在 core.yaml 加非标准 key。
- **修复 A 用"标题首词"判定**：非从属实体仅当 entity-id 是所属 section 标题的**首个** entity-id token 才算定义，兼消 `pollution_only` 与 `genuine_multi`（`### T-097 … C-001/C-002` 只定义 T-097）。
- **关系端点跨文档 parent 解析**：未在 `relation_extract` 做跨文档父解析，而是 `ExtractedRelation` 记 `object_doc`（xref 自带），writer 写关系时按 `(entity_id, source_doc)` 从库中解析从属端点真实 IRI；同号多父时取首个匹配（已知近似）。

## 参考

- 复现脚本：[`repro_diag.py`](./repro_diag.py)
- 缓解性提交：`#214`（`40030d9`）；根治：PR #219（修复 A）、PR #220（修复 B）
- 抽取器源码：`src/cataforge/domain/kg/ingest/{entity_extract,iri,relation_extract,writer,migrate,reconcile}.py`
