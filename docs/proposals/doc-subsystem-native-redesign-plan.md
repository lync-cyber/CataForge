# 落地计划：文档子系统原生化重设计（可执行分解 + framework-review 核实）

> 状态：已实施（配套 [`doc-subsystem-native-redesign.md`](doc-subsystem-native-redesign.md)，实施偏离与已决项见其头部）。以代码为准，本文余下为历史实施记录。
> 关系：提案讲「为什么 / 目标形态 / 决策」，本文件讲「改哪个文件的哪个函数 / 写什么 RED-first 测试 / 什么验收门 / 什么顺序」。§A 是 framework-review 静态核实结论（提案约定的双验之一，当下执行）；framework-walkthrough（动态端到端）留待各轨落地后。
> 证据源：主线程直读源码核实，锚点标 `file:function[:line]`。

---

## A. framework-review 静态核实结论

对提案触及的元资产 + 承重代码路径做静态审，确认前提、surface 新发现、定风险、resolve 决策。

### A.1 四债前提复核（全部成立）

| 债 | 前提 | 核实 |
|----|------|------|
| A | 图 `cf:Volume` 树是死 schema | `structure_extract.py:14` docstring「out of scope」；`writer.write_structure` 只写 Document+Section；grep 全 `domain/kg` 零 Volume 节点生产/消费 —— **成立** |
| A | 跨卷 `doc#§N` 两后端不透明 | 图 `_loader_kg._kg_section_body` 精确 `source_doc` 匹配；文件 `_resolve_doc_entry` 多卷抛 `AmbiguousRefError` —— **成立** |
| A | 无 split CLI / authoring 无卷参 | 全仓无 split 命令；`application/context` 无 `split_from`/`volume_type` —— **成立** |
| B | Layer 1 跨卷校验建于弱结构 | `check_xref` glob 只验文件、`check_bidirectional_coverage` 仅主卷字符串匹配、`check_split_consistency` 文本 glob —— **成立** |
| B | 「doc_consistency 多卷误计」 | **证伪**：`_read_all_content` 拼接全卷，regex 卷容忍；真实脆弱点是 KG 路径模糊子串 `CONTAINS "prd"` —— 诊断已按此修正 |
| C | references 反转、角色卡矛盾、守卫纯语法 | `generate.md:3`/`review.md:21` 反转；6 卡 md-first；`check_prompt_cli_drift` 纯语法 —— **成立** |
| D | 本体封闭、无逃生、未知前缀静默丢弃 | schema 打包无用户覆盖、`extra=forbid`、`plugins_dir` 死配置、`ENTITY_PREFIX_RE` 由封闭前缀集派生 —— **成立** |

### A.2 新发现（framework-review caliber）

- **F-1 · 卡 ↔ COMMON-RULES 直接矛盾（强于原诊断）**：COMMON-RULES §Agent 文档 I/O 契约明写「统一经 context 能力入口…定稿与回灌…后端由 `context.mode` 路由，调用方不分支」，但 6 角色卡 Output Contract 框定「产出 `{doc_type}.md`」+ `file_write`。债 C 不只是「references vs 卡」，是**共享规则 vs 卡**——P1 改卡是把卡对齐到既有 SSOT 规则，非引入新约定。
- **F-2 · 两态已在 CLI 层强制**：`write.py:_require_graph_mode` 在 markdown mode 下对所有 authoring 动词 `raise ContextModeError("edit the documents under docs/ directly instead")`。P1 改卡只是把卡对齐到**已强制的运行时行为**——低风险、纯措辞。
- **F-3 · `author_document` 本就产整篇单 Document**（`write.py:534`）：S1 的「授权整篇逻辑文档」在授权 API 基础态**无需新参**；工作量集中在①停止按卷分文件授权（角色卡+模板）②迁移合并存量分卷 Document。

### A.3 决策改判（§B 定稿）

- **决策 1 改判：删 `cf:Volume`，split 为导出侧纯函数**（初稿倾向「复活 Volume」）。深读 `author_document` + `compile_documents` 后定案：图本就是 `Document→Section`，分区可在 finalize 由 `split_layout` + `VOLUME_OWNED_ID_PREFIXES` 无状态算出，无需持久 Volume 节点；per-file baseline 成本与是否有 Volume 节点无关，故 Volume 节点零收益且复活它=重造债 A 的平行结构节点。**这正是详细计划阶段应 surface 的：追代码路径找到更干净的设计。**

### A.4 引入的漂移风险（静态核对）

- **无 prompt↔CLI 漂移**：P1/references 措辞用的动词（`context write-doc`/`write-narrative`/`transact`/`finalize`/`write-meta`）全部是 `context_cmd.py` 已注册的真实动词 —— `check_prompt_cli_drift` 不会告警。
- **schema↔python 镜像**：删 Volume + 加 DomainEntity 必须 regen `_generated/core_pydantic.py` + `subclass_axioms.ttl`（`scripts/codegen_kg_schema.py`）并同步 `iri.py`/`_config.py` 镜像映射，否则 `check_codegen_fresh.py` + `check_schema_python_parity.py` FAIL —— 这两个守卫是 O1/S1 的硬门。
- **run_local 覆盖**：新守卫 P2 必须接入 `run_local.py:CHECKS` 且过 `check_run_local_coverage.py`（元守卫：每个确定性 check_*.py 都要接线）。

### A.5 verdict

`approved_with_notes`：四债前提成立（B 一处已诚实修正），plan 可执行；notes = 决策 1 改判（§A.3）、schema 镜像/run_local 覆盖两道硬门（§A.4）须在对应轨内先接。framework-walkthrough 留待落地后。

---

## B. 目标结构模型定稿

- **图（graph mode）**：`cf:Document`（id=逻辑 doc_id）经 `cf:part_of_document` 持有其**全部** `cf:Section`。**无每卷独立 Document、无 `cf:Volume` 节点**。结构模型 = 纯 `Document→Section(→contains_entity)`。
- **导出（finalize）**：`split_layout[doc_type] = {threshold, partition}` 对 Document 全 Section 做**无状态分区**→ 发 N 个物理卷文件；每输出文件独立 baseline hash；派生 `split_from`/`volume_type` frontmatter；主卷含概览+交叉引用目录。未拆分=空 partition=单文件。
- **读（两 mode）**：寻址逻辑 doc_id；`arch#§N` graph→单 Document 的 Section，md→`logical_doc` 组索引定位物理卷。卷 id 不再是寻址单元。
- **校验**：跑在逻辑 Document（全卷并集）上，走严格解析，无 glob。
- **本体逃生阀**：core 40 类封闭 + 单一开放 `cf:DomainEntity{domain_type, has_attribute→DomainAttribute}` + `kg.custom_entity_prefixes` 注册；未注册前缀 doctor WARN。

---

## C. 可执行分解（按轨）

每项：**改动点** → **具体改法** → **RED-first 测试** → **验收门** → **依赖**。

### 轨-结构

**S1 · 图 SSOT 单一逻辑 Document + 删 `cf:Volume` 死 schema**
- 改动点：`domain/kg/schemas/core.yaml`（Volume 类 + `has_volume`/`part_of_volume` slots + `Section.part_of_volume` + `Document.has_volume`）；`_generated/core_pydantic.py` + `_generated/subclass_axioms.ttl`（`scripts/codegen_kg_schema.py` regen）；`domain/kg/validate.py`（结构类清单 `("Project","Document","Volume","Section")` 去 Volume）。
- 具体改法：从 core.yaml 删 Volume 类定义与两 slot 声明及其在 Document/Section 的引用；regen；validate.py SHACL target 去 Volume。authoring 基础态不改（`author_document` 已产整篇单 Document）；角色卡改「授权整篇逻辑文档、不按卷分文件」在 P1 落。
- RED-first 测试：`tests/kg/test_schema_no_volume.py` —— SchemaView 断言无 `Volume` 类、无 `has_volume`/`part_of_volume` slot；`test_codegen_fresh`/`check_codegen_fresh` 绿；`check_schema_python_parity` 绿。
- 验收门：`check_codegen_fresh.py` + `check_schema_python_parity.py` 0 退出；`validate` 对无 Volume 的 store 通过。
- 依赖：无（可先行；与 P、O 轨并行）。

**S2 · 读解析器逻辑文档透明**
- 改动点：文件后端 `domain/docs/_index_build.py:build_document_entry`（已读 `split_from`）+ `_make_index`（新增顶层 `logical_groups: {逻辑id: [doc_id...]}`）；`domain/docs/index_ops.py:_resolve_doc_entry` + `_lookup_in_index`（bare section ref 跨组查找）；图后端 `domain/docs/_loader_kg.py:_kg_section_body`（依赖 M1 使 section `source_doc` 归一到逻辑 id 后自然命中）。
- 具体改法：md 侧——`_make_index` 由各 entry 的 `split_from` 反查建 `logical_groups`；`_resolve_doc_entry` 对 `arch` 解析到逻辑组，`_lookup_in_index` 对 bare `§N` 在组内各卷 entry 顺序查 section（替代前缀单卷命中/歧义）。graph 侧——归一后 `_kg_section_body` 的 `source_doc "arch"` 直接命中，无需改查询。
- RED-first 测试：`tests/context/test_cross_volume_read.py` —— 造拆卷 fixture（§3 落在原 api 分卷），`context read arch#§3` 在 graph + markdown 两后端都返回该 section；多卷不再抛 `AmbiguousRefError`；纯 §-ref 与 item-ref 都透明。
- 验收门：跨卷读回归用例通过；旧前缀歧义用例转为透明解析。
- 依赖：S1（graph）、M1（迁移使 source_doc 归一）。

**S3 · 导出布局能力（split/merge 作无状态函数）**
- 改动点：`domain/kg/export/document_pipeline.py:compile_documents`（`_list_documents`→per-Document、`render_document`、`_section_bodies`、`set_exported_hash`/`_get_exported_hash` 的 baseline）；新增 `split_layout` 消费；`doc_review/constants.py:VOLUME_OWNED_ID_PREFIXES` 作默认分区。
- 具体改法：`compile_documents` 对每个 Document——按 `split_layout[doc_type]` 计算 section→卷分区（默认：section 按其 `contains_entity` 的 owned 前缀落卷；无 owned 前缀的叙事段→主卷；size 超阈时同前缀内 size-greedy 再分）；每分区 `render` 一个文件、发 `split_from`/`volume_type` 派生 frontmatter；**baseline 从 per-Document 改 per-output-file**（`exported_content_hash` 挂到 (doc_iri, output_path) 复合键）；drift triage/reconcile 相应按文件粒度。合卷=空/单分区。
- RED-first 测试：`tests/kg/test_export_split_layout.py` —— 一个大 Document 经 `split_layout` 发 N 文件、每文件 frontmatter 正确、`finalize→ingest→finalize` 字节幂等；未配 split_layout 时单文件（合卷）；per-file blocked/backup 生效。
- 验收门：字节幂等 golden（waterfall+agile fixture）；per-file baseline drift 正确。
- 依赖：S1。

### 轨-校验

**V1 · Layer 1 跨卷检查重写到逻辑结构**
- 改动点：`doc_review/checker.py:check_xref`、`check_bidirectional_coverage`、`check_split_consistency`、`check_split_header`；COMMON-RULES §Agent 文档 I/O 契约（补多卷覆盖矩阵语义）。
- 具体改法：`check_xref`——解析逻辑文档结构（图 SPARQL / md 逻辑组），验文档存在 + §/entity 在逻辑文档内存在；真损坏纯 §-ref → fail（不再静默跳过）。`check_bidirectional_coverage`——去 `volume_type != "main"` 早退，在逻辑组并集上跑（md）；图侧 `trace.bidirectional_coverage` 已全局 OK。`check_split_consistency`——graph mode 降为结构相等（导出卷集合 == `split_layout` 分区 且 每卷 `split_from` == 逻辑 id）；md mode 验 `split_from` 指向存在逻辑组 + 分卷 frontmatter 齐。COMMON-RULES 增一句「覆盖在逻辑文档全卷并集上计算，单卷不各自声明覆盖」。
- RED-first 测试：`tests/skill/doc_review/test_cross_volume_checks.py` —— 下游覆盖分散在分卷时 coverage 不假报 uncovered；跨卷 §-ref 不假报未找到；损坏 §-ref 报错；split 结构相等用例。
- 验收门：债 B 假阳性回归清零；多卷覆盖语义用例通过。
- 依赖：S1、S2。

**V2 · doc_consistency 精确逻辑成员判定**
- 改动点：`doc_consistency/checker.py:_kg_uncovered_acs` / `_kg_devplan_ac_coverage`（模糊 `CONTAINS "prd"`）；`doc_consistency/_parse.py:_find_docs`。
- 具体改法：KG 路径 `FILTER(CONTAINS(STR(?src),"prd"))` → 精确逻辑成员判定（`source_doc ∈ 逻辑组`）；`_find_docs` 由逻辑组索引驱动（替代 `docs/{doc_type}*.md` 裸 glob）。
- RED-first 测试：`tests/skill/doc_consistency/test_logical_membership.py` —— source_doc 含 "prd" 子串的无关文档不再误命中；分卷正确归组。
- 验收门：模糊子串假阳性清零。
- 依赖：S2。

### 轨-提示词+守卫

**P1 · 6 角色卡 Output Contract 两态措辞**
- 改动点：`.cataforge/agents/{product-manager,architect,ui-designer,tech-lead,qa-engineer,devops}/AGENT.md` 的 Output Contract + Anti-Patterns。
- 具体改法：Output Contract 换提案 §3.5 两态模板（graph：`context write-doc`/`write`/`write-narrative`/`transact` 落图 + finalize 导出只读视图、不 Write/Edit docs/；markdown：模板实例化后直编 docs/）；交付物改「{doc_type} 逻辑文档，拆卷由 finalize 布局、不手工造分卷」；architect 等卡 Anti-Pattern「禁止 Bash 除 `context read`」→ 放行 `context write*`/`finalize`。`tools`/`allowed_paths` 保留（markdown mode 需直写），由 P2 语义守卫锁死 graph 语境不直写。
- RED-first 测试：见 P2（守卫先落，P1 使守卫由红转绿）。
- 验收门：P2 守卫对 6 卡 PASS；`check_prompt_cli_drift` 绿；`check_no_design_residue`/`check_doc_structure`/`check_no_language_coupling` 绿。
- 依赖：无（挂已存在 authoring API）；与结构轨并行。

**P2 · 新语义守卫 `check_doc_authoring_invariant.py`（RED-first）**
- 改动点：新增 `scripts/checks/check_doc_authoring_invariant.py`；`scripts/checks/run_local.py:CHECKS` 接线；`.pre-commit-config.yaml` + `.github/workflows/test.yml`。
- 具体改法：骨架照搬 `check_prompt_cli_drift.py`（`REPO_ROOT`、`SCAN_GLOBS=[(.cataforge/agents,"**/AGENT.md")]`、code-fence + `ALLOW_MARKER=<!-- allow-doc-authoring`、返回 0/1/2、printed 报告）。判定：对 registry 声明的产文档角色，定位 `## Output Contract` 段——FAIL 若段内命中「产出/写入 …docs/… .md」或「{doc_type}.md」**且缺**两态限定词（`context finalize`/「导出视图」/「图后端就绪时」）；或提示资产无条件 `Write`/`Edit docs/`。escape hatch 同行 `<!-- allow-doc-authoring: <reason> -->`。
- RED-first 测试：`tests/scripts/test_check_doc_authoring_invariant.py` —— 内置 md-first fixture 卡 FAIL、两态 fixture 卡 PASS；escape hatch 生效。守卫落地时 6 卡尚未改 → 守卫**红**（正是 RED），P1 改完 → **绿**。
- 验收门：`check_run_local_coverage.py` 绿（新守卫已接线）；守卫 self-test 通过。
- 依赖：无（可先于 P1 落，驱动 P1）。

### 轨-本体（债 D 逃生阀）

**O1 · `DomainEntity` + `DomainAttribute` 加入 core.yaml + regen**
- 改动点：`domain/kg/schemas/core.yaml`（新类 + slots `domain_type`/`attr_name`/`attr_value`/`has_attribute`）；regen `_generated/*`；`_config.py:ENTITY_CLASS_TO_DOC_TYPE`（DomainEntity 归属处理）。
- 具体改法：`DomainEntity(is_a: SoftwareArtifact){ domain_type(required), has_attribute→DomainAttribute }`；`DomainAttribute(is_a: SoftwareArtifact 或独立){ attr_name, attr_value }`；`DomainEntity.entity_id` 用宽松 pattern（`^[A-Z]+-[0-9]{3,}$`，实际识别由 O2 的注册前缀集门控）；regen 过 `check_codegen_fresh`/`check_schema_python_parity`。
- RED-first 测试：`tests/kg/test_domain_entity_schema.py` —— SchemaView 有 DomainEntity/DomainAttribute + slots；regen 幂等。
- 验收门：codegen/parity 守卫绿。
- 依赖：无（可与 S1 并行；同 core.yaml 文件，注意与 S1 的 Volume 删除合并到一次 regen）。

**O2 · 识别前缀 config-aware + 注册 + 未知前缀 WARN + schema-context**
- 改动点：`domain/kg/ingest/entity_extract.py:ENTITY_PREFIX_RE`(:106) + `:308-311`；`domain/kg/ingest/relation_extract.py`（同类 skip 点）；`domain/kg/_dispatch.py`（新 `custom_entity_prefixes(project_root)` 解析器，读 `framework.json kg.custom_entity_prefixes`，缓存同 `active_doc_types`）；`iri.py:id_prefix_to_type`（注册前缀回退 DomainEntity）；`interface/cli/doctor/kg_ingestion.py:_home_doc_type`(:137)（未注册前缀 WARN）；`kg schema-context`（纳入 DomainEntity + 已注册 domain_type）。
- 具体改法：抽取前缀集 = core 前缀 ∪ 注册 custom 前缀；`ENTITY_PREFIX_TO_CLASS.get(prefix)` 对注册前缀返回 `DomainEntity`（并把 `domain_type` 从注册值填入抽取实体）；未注册且非 core 的前缀 → doctor `kg_ingestion_completeness` 产 WARN（非静默）；`DomainAttribute` 从实体段结构化属性抽取（形如 `- key: value` 或表格行）。
- RED-first 测试：`tests/kg/test_custom_prefix_domain_entity.py` —— 注册 `{"ORD":"Order"}` 后 `ORD-001` → `DomainEntity{domain_type:"Order"}` + `has_attribute` 可 SPARQL 查；`ORD-001 satisfies F-003` 边入图、`trace` 可达；未注册 `XYZ-001` → doctor WARN（断言 stderr 含提示，非零信号）；不注册时 core 行为字节不变。
- 验收门：注册/未注册两路径用例通过；core 回归零影响。
- 依赖：O1。

### 轨-迁移

**M1 · remerge 迁移 + framework.json + doctor**
- 改动点：`domain/kg/ingest/migrate.py`（remerge 分卷 Document 归并）；`framework.json` 经 `_merge_framework_json`（`docs.split_layout` + `kg.custom_entity_prefixes`，保留用户值）；`interface/cli/doctor/*`（新 split/本体检查）；`framework.json#migration_checks` 登记本次结构迁移。
- 具体改法：迁移——重扫卷文件，按 `split_from`/逻辑 id 归组，把各分卷 Document 的 Section `source_doc` 归一到逻辑 id 并归并到单逻辑 Document，删旧每卷 Document；`finalize` 按 `split_layout` 重发。config——`_merge_framework_json` 补 `docs.split_layout`（默认按 `VOLUME_OWNED_ID_PREFIXES`）+ `kg.custom_entity_prefixes`（默认 `{}`），全量覆盖 `features`/`migration_checks`。doctor——graph：每逻辑 id 单一 Document、无孤立每卷 Document、导出卷集合==分区；md：`split_from` 指向可解析逻辑组。
- RED-first 测试：`tests/e2e/test_split_volume_migration.py` —— 造存量「每卷独立 Document」项目，跑迁移后单逻辑 Document 持全 Section、`arch#§N` 透明、旧每卷 Document 消失、finalize 幂等。
- 验收门：迁移幂等；doctor 全绿；存量 md-mode 项目零改动通过。
- 依赖：S1、S3、O2。

**M2 · 双 mode framework-walkthrough**
- 改动点：无源码（验证工作）。
- 具体改法：`graph` / `markdown` 各跑一遍 framework-walkthrough，覆盖：authoring-only 产文档（零 Edit docs/*.md）、拆卷透明读、split 导出、DomainEntity 注册流、双 mode 降级。
- 验收门：两 mode 各 GO。
- 依赖：全轨（落地后）。

---

## D. 依赖图与推进顺序

```
并行三线起步：
  结构线   S1 ──► S2 ──► V1 ──► V2
              └─► S3 ──┘        │
  提示词线 P2(RED) ──► P1        │
  本体线   O1 ──► O2             │
                                 ▼
  迁移收口          M1 (依赖 S1+S3+O2) ──► M2 (依赖全轨)
```

- **可并行**：结构线（S1/S2/S3）⊥ 提示词线（P1/P2）⊥ 本体线（O1/O2）——三线互不阻塞。
- **S1 与 O1 同改 `core.yaml`**：合并为一次 regen（删 Volume + 加 DomainEntity 同批），避免两次 codegen 冲突。
- **P2 先于 P1**：守卫 RED-first 落地（红），P1 改卡转绿。
- **收口**：M1 需 S1+S3+O2 就绪；M2（walkthrough）在全部落地后。
- **优先级**：P2→P1（消债 C，风险最低、见效最快）+ O1→O2（消未知前缀静默丢弃）+ S1（结构根因）三线并行；V*/M* 随就绪推进。

## E. 风险与回滚

| 风险 | 缓解 |
|------|------|
| S3 per-file baseline 改动触及 drift/reconcile 核心，回归面大 | 先 golden 字节幂等 fixture（waterfall+agile）锁基线，再改；`compile_documents` 改动全程 dry-run 对账 plan |
| M1 remerge 误删 Section（source_doc 归一错） | 迁移前 `.nq` 快照；迁移 dry-run 输出归并计划；失败可从快照 restore（`ensure_store` 已有恢复路径） |
| S1 删 Volume 破坏某处隐式依赖 | grep 已确认零消费者；`check_schema_python_parity` + 全量 pytest 兜底 |
| P1 剥离 file_write 误伤 markdown mode | 决策 3 保留 tools，仅措辞+守卫锁 graph 语境；markdown mode 直编 docs 仍合法 |
| O2 config-aware 前缀集破坏抽取热路径性能 | 前缀集 per-project 缓存（同 `active_doc_types` 的 `_DISPATCH_LOCK` 缓存模式）；正则一次编译 |

**总回滚**：各轨独立可验收、独立可回退；结构线未落地前，提示词线/本体线的改动对存量行为向后兼容（不注册 custom 前缀、不配 split_layout 时字节不变）。

---

**双验状态**：framework-review（§A）已执行，verdict `approved_with_notes`；framework-walkthrough（M2）留待各轨落地后。落地进度以本仓 git 历史 + 本文件头部状态为准。
