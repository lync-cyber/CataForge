# 实施计划：kg-first 反转剩余序列 PR-C / PR-D / PR-E

> 状态：计划。本文是 `kg-first-authoring-inversion.md` §3 剩余子项（P-5 / P-4 / P-6）的落地拆分，由代码与提示词联合审查驱动。
> 映射：**PR-C = P-5**（审查/修订面）→ **PR-D = P-4**（工作流资产反转）→ **PR-E = P-6**（迁移与门禁收尾）。
> 交付边界：本文给出文件级改动清单、横切架构、验收标准与排序；实现以各 PR 的 git 历史为准。

---

## 0. 关键判断重定位

联合审查后，对剩余工作的性质判断与原提案有一处重要修正：

- **剩余工作的主体不是"新建子系统"，而是"翻转方向 + 收口关注点"**。P-1/P-2/P-3 的代码基底（whole-document 导出、authoring API、结构 authoring、补偿事务、三方哈希 triage）**已完整落地、无 stub**。导出覆盖全部 6 类 doc_type 且字节级幂等，两条渲染路径（document_pipeline / pipeline）职责正交、零重复。
- **原提案风险 #1（导出保真度）基本退场**：P-1 已打通全 doc_type；剩余保真缺口仅"表格 / 动态交叉引用"为列表/硬编码（非阻塞，留作增量）。
- **真正的剩余风险集中在两点**：(a) **权威方向当前被"记录但不执行"**——`reconcile` 捕获 `authoring_mode` 却不据其分流，提示词仍写 md 权威，形成"代码与提示词双脑分裂"；(b) **工作流资产的原子翻转**（PR-D）面大且不可半途。
- 因此 C/D/E 的代码改动是**少量精准收口**（reconcile 权威分流、ingest 来源模式、finalize 空图语义、doctor 门禁、read.py 关注点分离），**大头在提示词资产反转**。

---

## 1. 审查发现合并

### 1.1 代码层 — 已就位事实（不重做）

| 模块 | 文件 | 现状 |
|------|------|------|
| authoring API | `application/context/write.py` (842 行) | `author_entity` / `write_narrative` / `transact` / `author_document` 全实现；补偿 cascade-delete 零图遗留；占位符标题守卫齐备 |
| whole-document 导出 | `domain/kg/export/document_pipeline.py` | doc_type 无关，覆盖全 6 类；分卷各自重建；orphan 回落 per-entity 卡片 |
| per-entity 渲染 | `domain/kg/export/pipeline.py` + `render.py` | 与 whole-document 正交，共享 SPARQL→hydrate→Jinja 栈，零重复 |
| 字节幂等 | `document_pipeline.py:44,119` + `pipeline.py:6-14` | 固定 joiner + ORDER BY + StrictUndefined 三层保证，`finalize→ingest→finalize` 有测试 |
| 三方哈希 triage | `domain/kg/reconcile.py:105-176` | `never_exported` / `in_sync` / `human_edit` / `graph_ahead` / `conflict` 五态分类已实现 |
| 策略路由 | `application/context/router.py` + `_dispatch.py:119-173` | `context.strategy` 驱动 kg-first / doc-only；`authoring` 仅 kg-first 下可为 `graph` |

### 1.2 代码层 — 待收口隐患（C-编号）

| 编号 | 位置 | 问题 | 归属 PR |
|------|------|------|---------|
| **C1** | `application/context/read.py:55-151` | CLI 关注点泄漏到 application 层（argparse / print / json.dumps / stderr）；read.py 实为 CLI 入口，与 write.py 的纯函数风格不一致 | PR-D |
| **C2** | `write.py:803` finalize() 二级分支 | 空图无条件 `run_migration()` 种子回灌，**不感知 `authoring_mode`**；`authoring=graph` 下空图应产骨架而非 md 种子；无注释说明意图 | PR-D |
| **C3** | `write.py:811-828` ingest() | 无来源参数，无法区分"人类 diff 回流"与"LLM/种子主写入"；reconcile 能判 `human_edit` 但 ingest 盲处理 | PR-D（接口）/ PR-E（语义闭环） |
| **C4** | `reconcile.py:352` | `authoring_mode(project_root)` 被捕获写入报告但**逻辑从不使用**——对称 diff 与权威方向无关。这是 P0 提示词漂移的代码侧对应物 | PR-E |
| **C5** | `context_cmd.py:138,161` | 逆向依赖：`context` 反向 import `docs_cmd.run_index/run_validate`；别名（docs）应依赖被别名者（context），方向反了 | PR-D |
| **C6** | `kg/ingest.py:312` vs `context_cmd.py:393` | `kg reconcile` 与 `context reconcile` 命名重叠、作用对象不同，易混淆 | PR-D（消歧/文档） |
| **C7** | finalize/ingest/reconcile_check | `if not kg_enabled()` 三处重复，可提炼装饰器 | PR-D（随手） |
| **C8** | `export/templates/*.j2` + `hydrator.py:32-33` | 交叉引用路径硬编码 `../arch/`；`layout_spec`/`ui_route` 字段水合但无模板使用（隐活死字段） | PR-E（增量，非阻塞） |
| **C9** | `doctor/kg_ingestion.py` + `document_pipeline.py:152-189` | doctor 未校验 `strategy↔authoring` 约束有效性；orphan 实体无门禁 | PR-E |

### 1.3 提示词层 — 权威方向与 md-first 残留（P-编号）

| 编号 | 位置 | 当前措辞 | 问题 | 归属 PR |
|------|------|---------|------|---------|
| **P0** | `ORCHESTRATOR-PROTOCOLS.md:178` | "自动修复：跑 `context ingest`（以 markdown 为准回灌权威存储）" | kg-first 下权威方向**反向**，应为图权威重导出 | PR-E（与 C4 同步）|
| **P1** | `context/references/generate.md:8,14` | `Write docs/{doc_type}/...md` 建骨架；`context read` + `Edit` 填章节 | md-first 主写入路径，应改为 authoring API 序列 | PR-D |
| **P2** | PM/architect/tech-lead AGENT.md Output Contract (`:30/:33/:30`) | "必须产出 {doc_type}-{project}.md" | 指向 md 文件产出，未提图写入 | PR-D |
| **P2b** | `product-manager/AGENT.md:5` | `disallowedTools: shell_exec` | **硬阻塞**：authoring 经 `cataforge context` CLI 需 shell；其余 5 个产文档 Agent 均有 shell_exec | PR-D |
| **P3** | `context/references/review.md:15` | "经 navigate 按需加载被审文档与上游依赖" | 未声明审查对象为**导出视图（只读）**；revision 修复路径未区分 Edit vs authoring | PR-C |
| **P4** | `ORCHESTRATOR-PROTOCOLS.md:133,149` | revision 收口"漂移时 ingest 回灌"；inline-fix "Edit / context write-section 直接修复" | kg-first 下修复应 authoring 落图后 re-finalize，非 Edit 导出文件 | PR-C |
| **P5** | `context/SKILL.md:24-28` | 输出规范"生成/写入：持久化确认"过度抽象 | 未明确 kg-first authoring 生命周期；可单一事实源化 | PR-D |

> 提示词层无硬约束 1/2/3 违反（溯源引用 / 语言耦合 / 编号跳跃）；ORCHESTRATOR-PROTOCOLS 的两处 `allow-doc-structure` 为合法例外。

---

## 2. 横切架构原则（贯穿 C/D/E，关注点分离）

这些原则是"负荷良好的架构"的核心，各 PR 落地时遵循，避免再次腐化：

1. **AuthorityPolicy 作为单一决策点**（消解 C4 + P0 双脑分裂）。在 `domain/kg/` 引入 `AuthorityPolicy(strategy, authoring_mode)`，封装"漂移补救方向"的唯一判定：`graph_ahead → finalize（图→md）`、`human_edit → ingest（md→图）`、`conflict → 用户裁决`。`reconcile` / `finalize` / `ingest` 以及 ORCHESTRATOR-PROTOCOLS Step 5.3 全部引用同一策略语义，不各自写方向。提示词侧只描述"按 AuthorityPolicy 补救"，方向细节不复述（避免漂移）。

2. **CLI 与 application 分层归位**（C1）。`application/context/read.py` 剥离 argparse / print / json，回归纯函数返回数据；CLI 解析与输出格式化下沉到 `interface/cli/` 薄适配层——对齐 write.py 既有的纯函数风格。这是用户强调的"关注点分离"的最大单点。

3. **策略门控收敛为装饰器**（C7）。`@requires_kg_first` 替代 finalize/ingest/reconcile_check 三处重复的 `if not kg_enabled()`，门控逻辑单一来源。

4. **ingest 来源显式化**（C3）。引入 `IngestSource ∈ {seed, human_diff}`：`seed` 走 migration 全量灌入，`human_diff` 走人改回流（未来可加差异化校验）。当前两条混用同一 `run_migration`，需在 API 层分离意图，即便初期行为相同。

5. **提示词单一事实源**。kg-first authoring 生命周期（authoring→finalize→人审→ingest→reconcile）只在 context SKILL 的一个 reference 定义完整，`generate.md` / `review.md` / ORCHESTRATOR-PROTOCOLS / Agent Output Contract 以链接引用，不重述方向与命令——这正是本次审查发现漂移的根因预防。

6. **导出器交叉引用 helper**（C8，增量）。抽 Jinja filter `link_to(entity)` 动态解析 doc_type 前缀，替代模板硬编码 `../arch/`；同步退役或实现 `layout_spec`/`ui_route` 死字段。非阻塞，可独立增量。

---

## 3. PR-C（= P-5 审查/修订面适配）

**依赖**：仅 P-1（已就位）。可最先落地。
**核心命题**：审查只读导出视图；修订经 authoring 落图后 re-finalize，闭环不产生 md↔KG 漂移。

### 改动清单

**提示词**
- `context/references/review.md`：声明 Layer 1/2 审查对象为 `context finalize` 导出的**只读视图**；审查前若 reconcile 报 `graph_ahead`，先 finalize 再审，杜绝审陈旧 md。
- `context/references/review.md` + ORCHESTRATOR-PROTOCOLS Revision Protocol(`:133`)：revision 修复**经 authoring API 落图 → re-finalize**，不 Edit 导出文件；收口 reconcile 期望 `graph_ahead → finalize → in_sync`（修复 P4 的修订侧）。
- ORCHESTRATOR-PROTOCOLS Approved-with-Notes inline-fix(`:149`)：kg-first 下 LOW 批量修复改为 `context write` / `context write-narrative` 落图后 finalize，移除"Edit 导出文件"措辞（修复 P4 的 inline-fix 侧）。

**代码**
- doc-review checker（`runtime/skill/builtins/doc_review/checker.py`）：已文本友好，无需重构；补一处守卫——kg-first 项目运行 doc-review 前确保审查的是最新导出（reconcile 非 `graph_ahead`），否则提示先 finalize。

### 验收
- doc-review Layer 1 全检查项在导出视图上可执行（沿用既有 fixture）。
- revision 闭环：authoring 修复 → finalize → `context reconcile` 归零，无 `conflict`。
- 过渡兼容性说明：PR-D 未落地时初始生成仍 Edit→ingest，graph 经 ingest 同步，PR-C 的"修订走 authoring"与之共存（两者都使 finalize 可重导出）。

---

## 4. PR-D（= P-4 工作流资产反转）— 原子翻转

**依赖**：P-1 + P-2 + P-3（全部就位）。
**性质**：不可半途的原子翻转，提示词面最大。

### 改动清单

**4.1 context skill generate 流程反转**（P1）
- `context/references/generate.md`：
  - 创建骨架：`Write ...md` → 从模板实例化 **Document/Volume/Section 图骨架**（`context write-doc` / `context transact`）。
  - 写入章节：`context read` + `Edit` → authoring API（实体 `context write`、节叙事 `context write-narrative`、整章批量 `context transact`）。
  - 定稿：`context finalize` 导出视图；**ingest 仅吸收人改**（不再作主写入路径）。

**4.2 Agent Output Contract 改图写入**（P2 + P2b）
- PM / architect / tech-lead（及 ui-designer / qa-engineer / devops 产文档面）Output Contract：
  "通过 context authoring API 落图，`context finalize` 导出 `docs/{doc_type}/...md` 供审查"。
- **P2b 硬阻塞解除**：`product-manager/AGENT.md` frontmatter 补 `shell_exec`（authoring 经 CLI 必需）。架构决策记录：authoring 入口走 `cataforge context` shell 命令（SKILL `suggested-tools` 已含 Bash），不引入新原生工具——保持单一调用面。
- frontmatter `tools` 保留 file_read（读模板）/ file_write（research-note 等非文档产物）；文档正文不再经 file_edit 直写。

**4.3 权威方向门禁翻转**（P0 的提示词侧，与 PR-E 的 C4 代码侧呼应；若 PR-D 先落则先放条件分支）
- ORCHESTRATOR-PROTOCOLS Step 5.3(`:178`)：漂移补救按 AuthorityPolicy——kg-first `graph_ahead → context finalize 重导出`；`human_edit → context ingest`；移除"以 markdown 为准"绝对化措辞。

**4.4 CLI 动词收敛收尾**（P-4 剩余子项）
- C5：将 `run_index`/`run_validate` 共享实现归位（移到 `interface/cli` 共享 helper 或 context 侧），`docs_cmd` 别名反向 import，消除逆向依赖。
- 别名期管理：`docs load/index/validate` 加 Click `hidden=True` + stderr 弃用提示已有；明确别名期窗口。
- C6：`kg reconcile` 与 `context reconcile` 的 `--help` 消歧（低层工程 vs 高层策略守卫），或重命名低层为 `kg drift-check`。
- grep 守卫：新增 check，校验提示词资产引用的 CLI 命令面与实际命令零漂移。

**4.5 代码收口**
- C1：read.py 关注点分离（见 §2.2）。
- C2：finalize 空图分支感知 `authoring_mode`，加显式分支 + 注释。
- C3：ingest 增 `IngestSource` 接口（行为初期等价，意图分离）。
- C7：`@requires_kg_first` 装饰器。
- C2/C3/C7 共用 §2.1 的 AuthorityPolicy。

### 验收
- 提案 §2 端到端：product-manager 不经任何 `Edit docs/*.md`，仅经 authoring API 产出含 Feature/AC/叙事的完整 PRD；finalize 导出通过 doc-review L1+L2；人改一处叙事后 ingest 回流、reconcile 归零、再 finalize 字节幂等。
- `docs load` 实体级/章节级读取在反转前后内容一致；旧读取入口别名期行为不变。
- grep 守卫：全部 prompt 资产 ↔ CLI 命令面零漂移。

---

## 5. PR-E（= P-6 迁移与门禁收尾）

**依赖**：P-1~P-5。

### 改动清单

**5.1 reconcile 权威方向随 strategy 收敛**（C4，P0 代码侧闭环）
- `reconcile.py`：引入并消费 §2.1 的 AuthorityPolicy，使 `authoring_mode` 真正驱动补救默认方向，而非仅写报告。reconcile / finalize / ingest / Step 5.3 同源。

**5.2 下游迁移路径**（md-first → kg-first）
- 迁移流：`context ingest --source seed`（种子灌入）→ `context finalize --init-export-baseline`（首次全量重导出 + 写基线哈希）→ 切权威。
- `migrate.py` 补 `--init-export-baseline` 阶段（首次导出基线初始化）。
- framework-update 提示迁移路径；提供 md-first 过渡回退开关，保留 ≥1 minor 周期。

**5.3 doctor / walkthrough 适配**（C9）
- doctor：`check_context_strategy_validity()` 校验 `strategy=doc-only ⇒ authoring=md`、`authoring=graph ⇒ strategy=kg-first`；orphan 实体（无 Document 覆盖）门禁报告。
- framework-walkthrough：扩展 kg-first authoring 模式端到端演练（图写入 → finalize → reconcile 归零）。

**5.4 契约措辞终态化**
- 执行模式矩阵 / COMMON-RULES 的 context I/O 契约措辞对齐图权威终态。
- 开放问题决策：per-doc_type 权威粒度（如 prd 图权威、test-report 保持 md 权威）与运维类文档（deploy-spec/changelog）是否纳入反转——按 P-1 实测结论定稿并写入提案。

**5.5 导出器增量**（C8，可独立）
- `link_to(entity)` Jinja filter；退役/实现 `layout_spec`/`ui_route` 死字段。

### 验收
- `cataforge framework-walkthrough` 在 kg-first authoring 模式整链路 GO。
- md-first 存量项目按迁移文档切换后 `cataforge doctor` 全绿。
- reconcile 补救方向在 kg-first / md-first 两策略下均符合 AuthorityPolicy。

---

## 6. 排序与依赖

```
PR-C (P-5) ──┐  仅依赖 P-1，最先落地；与 PR-D 的初始生成路径可过渡共存
             │
PR-D (P-4) ──┤  原子翻转，依赖 P-1/2/3；落地 §2.1 AuthorityPolicy 的提示词侧 + read.py 分层
             │
PR-E (P-6) ──┘  依赖全部；闭合 C4 代码侧 + 迁移 + doctor/walkthrough 门禁
```

- **AuthorityPolicy（§2.1）建议在 PR-D 引入对象骨架**（提示词引用其语义），**PR-E 让 reconcile 真正消费**——避免 PR-D 提示词翻转后代码仍对称 diff 的窗口期。若希望窗口最短，可将 C4 提前到 PR-D。
- C8（导出器增量）非阻塞，可作为 PR-E 内独立 commit 或单独跟进。

## 7. 风险重估（相对原提案）

| 原风险 | 重估 |
|--------|------|
| #1 导出保真度 | **基本退场**：全 doc_type 已打通且幂等；仅表格/动态交叉引用为列表/硬编码，增量处理 |
| #2 LLM authoring 工效 | 仍需 walkthrough 实测：`context transact` 批量提交是工效成立前提，PR-D 切换前用 walkthrough 对比 authoring 序列 vs 单次 Edit 的成本 |
| #3 叙事归属 | 已由 P-1 模板的实体正文 vs Section narrative 边界处理（实体定义节走实体正文，非实体节走 Section narrative） |
| #4 混合权威过渡 | 由 AuthorityPolicy（strategy 驱动，非版本驱动）保证升级不即翻转 |
| **新增** 双脑分裂 | reconcile 记录但不消费 authoring_mode + 提示词仍写 md 权威——本计划以 §2.1 单一决策点 + §2.5 单一事实源消解 |
