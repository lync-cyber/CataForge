# 提案：context / kg 子系统整体修复 —— 收敛配置轴、统一分派、命令分层

> 状态：支柱一（mode 收敛）+ 支柱二（ModePolicy / R-003 reconcile 门禁 / R-004 授权门 + source_doc 保持）+ Track C（R-010 模板 xref + 多 xref 主语绑定修复 / M4 write-doc relations=0 告警 / R-011 M 级覆盖经 `cf:realizes` 真正生效 / 对称 diff card 假阳性收敛）已实现并通过全量测试；支柱三（命令分层）与卫生项（Track A/B/D、prompt 资产、framework-update 迁移）待续。
> 范围：`context` 与 `kg` 两个 CLI 模块的配置模型、能力分派、命令面，以及由其驱动的模板 / 覆盖门禁 / 走查 skill。
> 证据源：`docs/reviews/framework/FRAMEWORK-REVIEW-walkthrough-20260621-r1.md`（本轮走查 + 命令设计审查的全部 finding 与可复现命令）。
> 与既有提案的关系：本提案**取代** `kg-first-authoring-inversion.md` / `kg-first-inversion-pr-cde-plan.md` 中「strategy 与 authoring 两条正交配置轴」的设计决策；**保留并复用**其已落地的原语（`AuthorityPolicy`、`document_pipeline` 整篇导出器、三方哈希 drift triage、`context status` 探针）。详见 §8。

---

## 0. 一句话

当前 context/kg 子系统的腐化根源是**两条会互相矛盾的配置轴**（`context.strategy` × `context.authoring`）和**两套并行的用户命令面**（context 门面 / kg 底层）边界不清。修复目标不是逐条打补丁，而是：**把"谁是事实源"收敛为单一枚举 `context.mode`，把所有随模式而变的行为收敛到单一 `ModePolicy` 分派，把 context 收敛为唯一面向 Agent 的完整门面、kg 收敛为纯底层 store 机械。** 三件事做完，本轮发现的绝大多数 finding 在结构上不再可能复发。

---

## 1. 根因诊断

### 1.1 双轴正交 → 组合腐化（C1 / R-001 / R-004 / U4）

| 轴 | 取值 | 语义 |
|----|------|------|
| `context.strategy` | `kg-first` / `doc-only` | 图后端是否存在 |
| `context.authoring` | `md`（默认）/ `graph` | 谁是事实源 |

两轴相乘出四个格子，其中**三个有意义、一个无意义**，且默认格子最反直觉：

| strategy × authoring | 含义 | 状态 |
|----------------------|------|------|
| doc-only × md | 纯 markdown，无图 | 合理 |
| kg-first × md（**默认**）| markdown 是事实源、图是派生镜像 | 合理但**名实不符**：名曰 kg-first 却 md 权威 |
| kg-first × graph | 图是事实源、markdown 是导出视图 | 合理（文档化授权门的目标态） |
| doc-only × graph | 无图却声明图权威 | **无意义组合** |

腐化由此而生：
- **C1**：默认 `kg-first × md`，但 `generate.md` / COMMON-RULES I/O 契约 / 全部 `context write*` 授权门假设的是 `graph` 权威 → 默认配置与文档化工作流互斥。
- **R-001**：`finalize` 在 `authoring=md` 下做 md→KG 同步（不导出图→md）；走查实测「`exported 6 file(s)`（graph 模式）vs `indexed 0`（md 模式）」证明这是**配置门控的正确行为**，但因默认落在反直觉格子而表现为「静默 no-op」。
- **R-004**：graph 授权门只受 `_require_kg_first`（[`write.py:131`](../../src/cataforge/application/context/write.py) 只查 strategy、不查 authoring）守卫 → 在 `authoring=md` 下**被允许**写图，产出却被 finalize 忽略；`context write` 还会把已属文档的实体孤立成独立 doc，触发 doctor「跨文档实体坍缩 — 静默数据丢失」。
- **U4**：`authoring` 是承重轴却不在 scaffold framework.json 显式出现（默认隐式 md），运维不跑 `context status` 无从得知自己在哪个格子。

### 1.2 两套并行命令面 → 重复与不一致（D/M/C/U 系列）

`context` 自述是「strategy 路由的单一门面，调用方不点名图」，`kg` 是底层。但二者**用户可见面重叠且约定相反**：

- 重复动词：`context ingest`⟷`kg import`（D1）、`context finalize`(graph)⟷`kg export`（D2）、`context reconcile`⟷`kg reconcile`（D3）、`context write`⟷`kg add`（D4，自述 twin）。
- 门面残缺：无 `context delete`（M1）、无 context 实体就地更新（M2）、context 状态/门禁类命令缺 `--json`（M3）。
- 约定相反：`context status` 恒裸 JSON、kg 默认人类表+`--json`（U2）；`--project-root` 在 context 内部 None vs "."、context（裸 str）vs kg（`click.Path(exists=True)`）不一（C3）；store 定位 context 走 `--project-root`、kg 走可 desync 的 `--db-path`（C4-store）；kg 内 `delete --yes` vs `rollback --force`（C5）。
- 门面泄漏：导出/删除/reconcile 明细/repair 都被迫跳到 kg，「单一门面」承诺落空（U3 / U1 / R-006）。

### 1.3 模式无关的独立正确性缺陷

与上面两条结构问题无关、可独立修：
- **R-003**：`context reconcile` 用 per-doc-type 实体级对称 diff 的 `overall_divergence_count` 当门禁结论，而该 diff 有 FS 重抽取**假阳性**（干净 graph 项目实测：文档级 triage `in_sync/none` ✓，对称 diff 却报 5 处「missing」）。权威结论与门禁结论脱节。
- **R-010**：lite 模板覆盖字段用裸 prose（`对应功能: F-001`），而关系抽取器 [`relation_extract.py`](../../src/cataforge/domain/kg/ingest/relation_extract.py) 只认 `doc_id#§N.ITEM` xref → write-doc 抽 0 边；`context write-doc` 还缺 `kg import` 已有的 `relations=0` 告警（M4）。
- **R-011**：dev-plan（M 级）覆盖门禁因 `bidirectional_coverage()` 只产 Feature(F) 行而空泛通过。
- **R-005**：skill-run 自动事件 phase 取自 CLAUDE.md 当前阶段，滞后即错相。
- **R-007**：`phase status` 缺 `--project-root`。
- **R-008**：CLAUDE.md 模板节名「项目信息」与协议引用「框架元信息」不一致。
- **D6**：`context validate` ≈ `context index --strict --dry-run`，实现重复。

---

## 2. 目标架构（三支柱）

### 支柱一 · 单一事实源枚举 `context.mode`

废除 `strategy` × `authoring` 双轴，收敛为**单一三值枚举**，每个值是一个内部自洽、不可与他者矛盾的模式：

| `context.mode` | 事实源 | 图后端 | 取代的旧组合 |
|----------------|--------|--------|-------------|
| `markdown` | markdown | 无 | doc-only |
| `hybrid`（建议默认）| markdown | 派生只读索引（供 read / coverage / trace 门禁）| kg-first × md |
| `graph` | 图 | 事实源 | kg-first × graph |

- **无意义组合在结构上消失**（`doc-only × graph` 不可表达）。
- **默认 `hybrid`**：既保住框架核心价值（KG 驱动的覆盖/追溯门禁默认可用），又让 markdown 仍是低 token 成本、人友好的授权底料；`graph`（LLM 直写图、md 为导出视图）成为**显式 opt-in**——即既有提案追求的「反转」，在新模型里就是「从 hybrid 切到 graph」，语义清晰、可回退。
- **向后兼容读取**：`framework.json#/context.mode` 缺失时，由旧 `strategy`+`authoring` 推导（`doc-only→markdown`、`kg-first×md→hybrid`、`kg-first×graph→graph`），doctor 提示迁移。一个 minor 周期后移除旧字段读取。
- **可见性**：deploy 把 `context.mode` 显式写入 framework.json，CLAUDE.md 框架元信息镜像该值（消解 U4）。

### 支柱二 · 单一 `ModePolicy` 分派

把所有「随模式而变」的行为收敛到**一个策略对象**（在现有 `AuthorityPolicy` 上演进，键从双轴改为单一 `mode`），任何门都不得自行写分支：

| 行为 | `markdown` | `hybrid` | `graph` |
|------|-----------|----------|---------|
| 授权门（write/write-doc/transact）| 不可用（提示编辑 docs/）| 不可用或自动「stage md→ingest」| 可用（写图）|
| `finalize` | 重建索引 | md→KG 同步 + 索引 | KG→md 导出 + 索引 |
| `reconcile` 权威方向 | 索引完整性 | md 权威（drift→ingest）| 图权威（drift→export）|
| `reconcile` 门禁结论 | 索引有效性 | 文档级 triage state | 文档级 triage state |
| coverage 门禁数据源 | 文件串扫描 | KG SPARQL | KG SPARQL |

要点：
- **消解 C2/C4「记录但不消费」**：`finalize`/`ingest`/`reconcile`/Phase Transition Step 5.3 全部引用同一 `ModePolicy.remediation_for(state)`，不各自编码方向。
- **消解 R-003**：门禁结论统一取**文档级三方哈希 triage state**（`in_sync`/`human_edit`/`graph_ahead`/`conflict`），per-doc-type 对称 diff **降级为诊断明细**（`--json` 里输出，不作 exit 判据）。对称 diff 的 FS 重抽取假阳性作为独立正确性项另行收敛（见 Track C），但即便未修也不再阻塞门禁。
- **消解 R-004**：授权门可用性由 `ModePolicy` 单点裁定——`hybrid`/`markdown` 下 graph 授权门直接拒绝（清晰报错指向正确流程）或自动路由，不再出现「写了图却被忽略」。
- **门控装饰器**：`finalize`/`ingest`/`reconcile_check` 三处重复的 `if not kg_enabled()` 收敛为 `@requires_mode(...)` 单一来源（消解 C7）。

### 支柱三 · 命令分层：context = 完整门面，kg = 纯底层机械

明确两层职责、消除用户可见面重叠：

- **`context`（唯一面向 Agent 的门面）**：完整覆盖业务生命周期——`read` / `write` / `write-narrative` / `write-doc` / `transact` / `update`（新）/ `delete`（新）/ `finalize` / `ingest` / `reconcile` / `validate` / `index` / `status`。全部命令：①统一 `--project-root`（`click.Path`，缺省 None 接全局 `--project-dir`）；②状态/门禁类全部支持 `--json`；③默认人类可读输出。
- **`kg`（纯底层 store 机械，非常规业务流程入口）**：`init` / `snapshot` / `rollback` / `repair` / `query` / `trace` / `validate`（图级 SHACL/orphan）/ `diff` / `schema-context`。这些是运维/调试/迁移工具，**不与 context 业务授权重叠**。
- **去重收敛**：`kg import`→由 `context ingest` 唯一暴露（kg 侧降为内部/隐藏）；`kg export`→由 `context finalize` 唯一暴露；`kg reconcile`→重命名 `kg drift-check` 并标注「低层对称 diff 诊断」，业务门禁只用 `context reconcile`；`kg add`/`update`/`delete` 保留为「无校验底层 twin」，文档明确「业务恒用 context」。
- **分层归位（C1-代码侧）**：`application/context/read.py` 剥离 argparse/print/json，回归纯函数；CLI 解析与格式化下沉 `interface/cli/`，对齐 `write.py` 既有纯函数风格。
- **逆向依赖修复（C5-code）**：`context` 不再反向 import `docs_cmd`；共享实现归位到 `interface/cli` 公共 helper，别名（`docs *`）单向依赖被别名者。

---

## 3. findings → remediation 全映射

| finding | 严重度 | 归属支柱/轨 | remediation 要点 |
|---------|--------|------------|-----------------|
| C1 默认组合矛盾 | HIGH | 支柱一 | `mode` 单枚举，默认 `hybrid`，消除矛盾格子 |
| R-001 finalize 静默 no-op | HIGH | 支柱一+二 | 模式收敛后 finalize 行为由 ModePolicy 单点定义；不可能再「写图却 indexed 0」 |
| R-004 graph 门孤立/无守卫 | HIGH | 支柱二 | ModePolicy 裁定门可用性；`context write` 对已属文档实体就地更新保 part_of |
| R-003 reconcile 假阳性门禁 | HIGH | 支柱二 | 门禁取文档级 triage state；对称 diff 降级诊断 |
| R-010 模板 prose 非 xref / 无告警 | HIGH | Track C | 模板覆盖字段改 `#§` xref；write-doc 补 `relations=0` 告警（M4）|
| R-011 M 级覆盖空泛通过 | MEDIUM | Track C | `bidirectional_coverage()` 产 M 行，或 checker 在无法覆盖某 prefix 时显式 SKIP+告警 |
| D1 ingest⟷import | — | 支柱三 | import 降底层/隐藏，ingest 为唯一门面 |
| D2 finalize⟷export | — | 支柱三 | export 降底层，finalize 为唯一门面 |
| D3 reconcile⟷reconcile | — | 支柱三 | kg reconcile→`kg drift-check` 低层诊断 |
| D4 write⟷add | — | 支柱三 | 文档化 twin 边界（校验门面 vs 无校验底层）|
| D6 validate⟷index --strict | LOW | Track B | validate 实现为 `index --strict --dry-run` 别名，单实现 |
| M1 无 context delete | MEDIUM | 支柱三 | 增 `context delete`（ModePolicy 路由）|
| M2 无 context 实体更新 | MEDIUM | 支柱三 | 增 `context update`（就地合并，保 part_of）|
| M3 context 缺 --json | MEDIUM | 支柱三 | 状态/门禁命令补 `--json` |
| M4 write-doc 无 relations=0 告警 | MEDIUM | Track C | 复用 `kg import` 同款告警 |
| C2 finalize 空图不感知模式 | LOW | 支柱二 | 由 ModePolicy 单点分派 |
| C3 --project-root 不一致 | MEDIUM | Track B | 统一 `click.Path` 类型 + 缺省 + 全局 --project-dir |
| C4 reconcile 记录不消费方向 | MEDIUM | 支柱二 | ModePolicy 真正驱动方向 |
| C4-store db-path 可 desync | LOW | 支柱三 | `--db-path` 标注高级用；常规走 --project-root |
| C5 delete --yes vs rollback --force | LOW | Track B | 统一 `--yes`=跳确认、`--force`=越安全检查 |
| C5-code 逆向依赖 | LOW | 支柱三 | 共享 helper 归位 |
| C7 门控重复 | LOW | 支柱二 | `@requires_mode` 装饰器 |
| U1 reconcile 藏 remediation | LOW | 支柱三 | = R-006 |
| U2 status 输出形态相反 | LOW | Track B | 统一默认人类 + `--json` |
| U3 门面泄漏 | — | 支柱三 | 补齐 delete/update/--json/reconcile 明细 |
| U4 authoring 不可见 | LOW | 支柱一 | `mode` 显式写 framework.json + CLAUDE.md |
| R-005 事件 phase 错相 | LOW | Track B | 事件 phase 由被审产物 doc_type 推断或显式传入 |
| R-006 reconcile 无明细/--json | LOW | 支柱三 | context reconcile 补 --json + 明细 + 报告路径 |
| R-007 phase status 缺 --project-root | LOW | Track B | 增 `--project-root` |
| R-008 CLAUDE.md 节名不一致 | LOW | Track B | 统一节名 |
| P-001 子代理 host cwd | HIGH(process) | Track D | walkthrough 协议明示主线程内联驱动 |
| P-002 协议依赖 finalize 导出 | MEDIUM(process) | Track D | 协议标注模式相关的导出命令 |
| P-003 env-block exit 2 预期 | LOW(process) | Track D | rubric 列为 non-finding |
| P-004 reconcile 明细获取 | LOW(process) | Track D | rubric 指明 `--json`/报告（R-006 落地后自然解决）|

---

## 4. 实施序列（依赖驱动，无冗余）

```
R0 基座（支柱一+二）──┬─ Track A 门面收敛（支柱三）
  mode 枚举收敛       │   delete/update/--json/去重/分层
  + ModePolicy 单点   │
                      ├─ Track B 独立 CLI 卫生（与模式解耦，可立即并行）
                      │   phase status --project-root / --project-root 一致 /
                      │   validate 去重 / flag 命名 / 事件 phase / 节名 / status 输出
                      │
                      ├─ Track C 模板/抽取/覆盖正确性（与模式解耦）
                      │   模板 xref / write-doc 告警 / M 级覆盖 / 对称 diff 假阳性
                      │
                      └─ Track D 走查 skill 自身（纯文档）
                          P-001~P-004 references 更新
```

- **R0 是基座**：支柱一（mode 收敛）+ 支柱二（ModePolicy）必须先落，因为 Track A 的门面行为、R-001/R-003/R-004 的结构性消解都依赖它。R0 内部：先加 `context.mode` 读取 + 兼容推导 + `ModePolicy(mode)`，再把 finalize/ingest/reconcile/授权门逐个改为单点分派。
- **Track B / C / D 与 R0 解耦**，可并行先落地（它们是独立正确性/卫生项，不碰模式语义）。建议 B/C/D 先行交付以快速降低风险面，R0 + A 作为结构性大改随后。
- **原子性约束**：支柱一的 mode 收敛是「不可半途」的——旧双轴读取与新 mode 读取不能长期并存于不同门，否则重现「双脑分裂」。R0 一次性把所有读取点切到 `ModePolicy`。

---

## 5. TDD 测试设计（先写复现测试 → 再修；每条均可复现）

> 约定：测试落 `tests/`，命名表意；先让其在现状 **RED**，修复后 **GREEN**。

### 5.1 支柱二 / R-003 —— reconcile 门禁取权威 state

- `test_clean_graph_roundtrip_reconcile_is_ok`：fresh `mode=graph` 项目，write-doc 一篇 prd → finalize → `reconcile_check` 返回 `ok=True`（文档级 `in_sync`）。**现状 RED**（`overall_divergence_count=5` → not ok）。修复：`reconcile_check.ok` / `context reconcile` 退出判据取文档级 triage state。
- `test_symmetric_diff_demoted_to_diagnostic`：同上项目 `context reconcile --json` 输出含 per-doc-type 明细但 `ok=True`、exit 0。

### 5.2 支柱二 / R-004 —— 授权门守卫 + 就地更新

- `test_graph_door_rejected_in_hybrid_mode`：`mode=hybrid` 下 `context write` 报清晰错误（指向 markdown 授权或建议切 graph），不静默写图。**现状 RED**（被允许）。
- `test_context_write_relation_preserves_part_of`：write-doc 一篇 arch（含 M-001）→ `context write M-001 --relation implements=F-001` → 断言 M-001 仍 `part_of` arch 文档、**无** `docs/arch/M-001.md`、`doctor` 无「跨文档实体坍缩」。**现状 RED**。

### 5.3 支柱一 / R-001 —— finalize 行为由 mode 单点定义

- `test_finalize_graph_exports_kg_to_md`：`mode=graph` 空 docs/ + 非空图 → finalize 导出 md。
- `test_finalize_hybrid_syncs_md_to_kg`：`mode=hybrid` → finalize 做 md→KG + 索引，不报「indexed 0」当 docs/ 实有内容。
- `test_no_silent_indexed_zero_on_graph_authored_content`：回归——杜绝「写图后 finalize 静默 indexed 0」。

### 5.4 Track C / R-010 / M4 —— 模板 xref + 抽取告警

- `test_writedoc_warns_when_coverage_prose_yields_zero_relations`：write-doc 一篇含 `对应功能: F-001`（裸 prose）且抽出 0 关系 → stderr 告警。**现状 RED**。
- `test_arch_template_coverage_uses_xref_and_extracts_implements`：以更新后的 arch-lite 模板实例化 → write-doc → SPARQL 断言 `M cf:implements F` 边存在（模板改 `#§` xref 后）。**现状 RED**。
- `test_relation_subject_binds_to_entity_not_trailing_ac`：覆盖 xref 紧跟 Task/Module 标题时主语为该实体（防 dev-plan 那种绑到末尾 AC）。

### 5.5 Track C / R-011 —— M 级覆盖门禁

- `test_devplan_coverage_fails_when_module_unimplemented`：dev-plan 的 M 无任何 Task `cf:realizes` → doc-review FAIL。**现状 RED**（空泛 PASS）。修复二选一：`bidirectional_coverage()` 产 M 行；或 checker 在 trace 不支持该 prefix 时显式 SKIP+告警（不静默判过）。

### 5.6 Track B —— 独立 CLI 卫生

- `test_phase_status_accepts_project_root`（R-007）：`phase status --project-root <p>` 作用于 p。**现状 RED**。
- `test_context_commands_project_root_consistent`（C3）：所有 context 命令 `--project-root` 同类型/缺省，且尊重全局 `--project-dir`。
- `test_validate_equals_index_strict_dryrun`（D6）：同输入下二者结论一致。
- `test_kg_destructive_commands_confirm_flag_consistent`（C5）：delete/rollback 跳确认 flag 命名一致。
- `test_skillrun_event_phase_reflects_reviewed_doc`（R-005）：CLAUDE.md phase=planning 时审 dev-plan，事件 phase 不取陈旧值。
- `test_context_status_human_default_and_json_flag`（U2）：默认人类可读、`--json` 切机读。
- `test_claude_md_section_name_matches_protocol_refs`（R-008）：模板节名与协议引用一致（grep 守卫）。

### 5.7 支柱三 / 门面完整化

- `test_context_delete_exists_and_routes`（M1）、`test_context_update_in_place`（M2）、`test_context_reconcile_json`（M3/R-006）。
- `test_context_facade_covers_lifecycle_without_kg`：以纯 `context` 命令完成 read→write→finalize→reconcile→delete 全生命周期，不调用任何 `kg *`（门面自足性回归，守 U3）。

---

## 6. 去重 / 删除清单（防腐）

| 动作 | 对象 | 理由 |
|------|------|------|
| 收敛配置 | `context.strategy` + `context.authoring` → `context.mode` | 双轴正交是组合腐化根源 |
| 降为底层/隐藏 | `kg import` / `kg export` | 与 `context ingest` / `context finalize` 重复用户面 |
| 重命名+降级 | `kg reconcile` → `kg drift-check`（低层诊断）| 与 `context reconcile` 命名冲突、职责重叠 |
| 提炼 | finalize/ingest/reconcile 三处 `if not kg_enabled()` → `@requires_mode` | 重复门控 |
| 别名归一 | `context validate` = `index --strict --dry-run` | 实现重复 |
| 归位 | `docs_cmd` ↔ `context` 逆向依赖；共享 helper 下沉 | 依赖方向错误 |
| 纯函数化 | `application/context/read.py` 去 CLI 关注点 | 与 write.py 风格不一 |

**反例守卫**：新增 grep check，校验所有 prompt 资产（SKILL/AGENT/PROTOCOLS）引用的 CLI 命令面与实际命令零漂移（防再次出现「提示词写 graph 权威、默认配置却 md」的双脑分裂）。

---

## 7. 迁移与兼容

- **配置迁移**：`context.mode` 缺失时由旧 `strategy`+`authoring` 推导（§2 支柱一映射）；`framework-update` / `deploy` 写入显式 `context.mode`；doctor 校验 mode 合法性并对旧字段告警。保留旧字段读取 ≥1 minor 周期后移除。
- **存量项目**：`markdown`/`hybrid` 项目零感知（默认即 hybrid，等价旧默认）；切 `graph` 走「`context ingest` 种子 → `context finalize` 首次全量导出 → 改 `context.mode=graph`」，全部由现有命令承载，提供回退（改回 hybrid）。
- **doctor 门禁**：`check_context_mode_validity()` 取代 strategy↔authoring 有效性校验；orphan 实体（无 Document 覆盖）门禁保留。

---

## 8. 与既有提案的关系

- **取代**：`kg-first-authoring-inversion.md` / `kg-first-inversion-pr-cde-plan.md` 中「strategy 与 authoring 两条正交轴 + authoring=md 过渡默认」的**配置模型决策**。本提案证明该正交性本身即腐化根源（走查实测：默认格子与文档化授权门互斥、graph 门在 md 下无守卫、两套 reconcile 语义并存）。
- **保留并复用**：既有提案**已落地的代码原语**——`AuthorityPolicy`（演进为 `ModePolicy`，键由双轴改单 mode）、`document_pipeline` 整篇导出器、三方哈希 drift triage、`context status` 探针、CLI 别名隐藏机制。这些是好资产，不重做。
- **重新定位「反转」**：既有提案的「md→graph 权威反转」在新模型里就是「`mode` 从 `hybrid` 切到 `graph`」——一个一等公民的显式模式切换，而非跨多个 minor 周期的过渡窗口；语义清晰、可回退、可被 doctor 校验。
- **建议**：本提案获采纳后，将上述两份提案标注为「配置模型部分被 context-kg-subsystem-remediation 取代；已落地原语清单见 §1.1」，避免三份文档并存造成新的事实源分裂。

---

## 9. 验收（总）

- 配置层：`framework.json` 仅 `context.mode` 一个事实源轴；旧双轴组合不可表达；doctor 校验通过。
- 行为层：finalize/ingest/reconcile/授权门可用性/coverage 数据源全部经 `ModePolicy` 单点分派；grep 守卫证提示词↔CLI 零漂移。
- 命令层：纯 `context` 命令可完成全业务生命周期（§5.7 回归）；`kg` 无业务授权重叠；全 context 命令 `--project-root`/`--json`/输出形态一致。
- 正确性：§5 全部 RED 测试转 GREEN；`cataforge framework-walkthrough` 在 `hybrid` 与 `graph` 两模式下整链路 GO。
