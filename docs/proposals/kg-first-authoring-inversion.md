# 提案：kg-first 权威反转 — LLM 直写知识图谱，markdown 降级为导出审查视图

> **取代说明**：本提案的**配置模型决策**（`context.strategy` × `context.authoring` 两条正交轴 + `authoring=md` 过渡默认）已被 [`context-kg-subsystem-remediation.md`](context-kg-subsystem-remediation.md) 取代为单一 `context.mode` 枚举（`markdown` / `hybrid` / `graph`）；已落地的代码原语（`AuthorityPolicy`→`ModePolicy`、`document_pipeline` 导出器、三方哈希 triage、`context status` 探针）保留复用。本文余下内容为历史设计记录。
> 状态：实施中。已落地：P-1 / P-2、P-3 结构 authoring、P-4 的 CLI 动词收敛子项、P-6 前置的权威 triage（reconcile 文档级三方哈希 + `context.authoring` 开关 + `context status` 探针）。剩余：P-5 审查/修订面 → P-4 工作流资产反转 → P-6 迁移与门禁收尾，按依赖链计划在 cloud 远程会话实施。
> 范围：context 能力面（authoring / finalize / ingest / reconcile）、KG 导出器、context skill 与产文档 Agent 的工作流资产、Phase Transition 门禁方向
> 交付边界：方案 + PR 序列为本文职责；已落地代码以 git 历史为准，剩余子项的拆分与验收标准见 §3。

---

## 0. 总体判断

kg-first 的声明设计意图是**图谱为唯一事实源**：LLM 把结构化实体与叙事直接写进图（写时校验），markdown 仅作为导出的人审视图；人类对导出视图的修订经 ingest 回流图谱。当前实现（含实体正文进图、镜像保真度、写面策略路由等基底修复）落地的仍是**markdown 为事实源、KG 为同步镜像**——authoring 反转未实现。本提案把差距分解为六个可独立验收的 PR 主题。

## 1. 设计意图与现状差距

### 1.1 意图原文证据

| 出处 | 原文 |
|------|------|
| `cataforge setup --context-strategy` help | "kg-first: **the graph is the source of truth**, `cataforge kg export` renders markdown **for human review**." |
| `src/cataforge/application/context/write.py` 模块 docstring | "authoring writes **go to the graph** under write-time schema validation, then Markdown is *exported* as a human-review view (finalize). **Human edits** to the exported Markdown are reflected back with ingest… **This inverts the legacy `write md → kg import` projection**." |

即 `ingest` 的设计角色是吸收**人类**对导出视图的修订，不是 LLM 的主写入路径。

### 1.2 现状差距（已逐项核实）

1. **导出器无整篇文档重建**：`compile_to_markdown` 的实体清单要求 `cf:entity_id + cf:sort_key`，Document / Volume / Section 节点不在导出范围；finalize 对非空图只产 per-entity 卡片（`docs/{doc_type}/{entity_id}.md`），无法重建 `prd-xxx.md` 人审版式（其 docstring 自承 lossy round-trip，空图分支故意不回导）。
2. **authoring API 残缺**：`Transaction.add_entity` 无 `parent_id` 参数——经 `context write` 写 AC 得到扁平 IRI、不挂 `part_of`；implements / satisfies / verifies 等关系边在 `context` 能力面无 authoring 入口（仅低层 `kg add`）；实体 narrative 只能经 `--slot` 传单行字符串；无多实体原子事务。
3. **工作流资产指向 md 先行**：context skill 生成流程为"模板实例化 → Edit 填章节 → finalize/ingest"；doc-review、doc-index、人审全部工作在 markdown 上。
4. **门禁方向编码了 md 权威**：ORCHESTRATOR-PROTOCOLS Phase Transition Step 5.3 的漂移处置为 "`context ingest`（以 markdown 为准回灌）"——在图权威下方向相反。

## 2. 目标形态（完全态工作流）

```
[Agent] context authoring API ──写时校验──▶ [KG 图谱（唯一事实源）]
                                              │ finalize
                                              ▼
                                  [docs/*.md 整篇导出视图（人审版式）]
                                              │ 人审 / 人改
                                              ▼ ingest（仅吸收人类 diff）
                                          [KG 图谱]
                                              │ reconcile（权威方向 KG→md）
                                              ▼
                                       Phase Transition 守门
```

**端到端验收标准**：在 kg-first 项目中，product-manager 角色不经任何 `Edit docs/*.md` 操作，仅经 context authoring API 产出一份含 Feature / AC / 叙事章节的完整 PRD；`context finalize` 导出的 markdown 通过 doc-review Layer 1 + Layer 2；人工修改导出文件一处叙事后 `context ingest` 回流，`context reconcile` 归零；再次 finalize 字节级幂等。

## 3. 缺口分解与 PR 序列

| 序号 | 主题 | 核心内容 | 依赖 |
|------|------|---------|------|
| P-1 | whole-document 导出器 | 按 Document→Volume→Section 树 + Section narrative + 实体正文重建整篇 markdown（人审版式）；finalize 以此替代 per-entity 卡片形态（卡片渲染保留为实体级读取面）；导出→ingest→导出 字节级幂等 | 无（数据基底已就绪） |
| P-2 | authoring API 完备化 | `add_entity` 增 `parent_id`；`context write` 支持 part_of 归属与关系边声明；narrative 经 stdin / 文件写入；`context transact` 多实体原子事务（amendment 单事务提交，失败整体回滚） | 无 |
| P-3 | 结构 authoring | 从模板实例化 Document / Volume / Section 图骨架（替代 Write md 骨架文件）；章节叙事经 write-narrative 填充 | P-2 |
| P-4 | 工作流资产反转 | context skill generate 在 kg-first 下改为 "authoring 序列 → finalize 导出 → 返回导出路径"；产文档 Agent（product-manager / architect / tech-lead 等）Output Contract 改为图写入；Step 5.3 权威方向翻转（ingest 仅人改回流，Agent 侧漂移按图重导出）；CLI 读写动词收敛到 `context` 单族（`docs load` / `context read` 双门面整理，旧入口保留别名期）；项目指令模板"加载原则"措辞对齐为"章节/条目"粒度 | P-1 + P-2 + P-3 |
| P-5 | 审查面适配 | doc-review 消费导出视图（只读）；revision 修复经 authoring API 落图后重新 finalize，而非 Edit 导出文件 | P-1 |
| P-6 | 迁移与门禁收尾 | 下游 md-first 项目切换路径（ingest 种子灌入 → 切权威 → 首次全量重导出）；reconcile 权威方向随 strategy 收敛；doctor / walkthrough 适配；执行模式矩阵与 COMMON-RULES 契约措辞终态化 | P-1~P-5 |

**并行性**：P-1 ⊥ P-2 可并行；P-3 在 P-2 后；P-4 必须等 P-1/P-2/P-3 全部就绪（工作流切换是不可半途的原子翻转）；P-5 仅依赖 P-1，可与 P-2/P-3 并行。

### 各项验收标准

- **P-1**：对既有 fixture 项目执行 `ingest → finalize`，导出文件与源 markdown 在规范化（标题锚点、空行折叠）后语义等价；`finalize → ingest → finalize` 字节级幂等；golden 基线覆盖 waterfall / agile 两套 fixture。
- **P-2**：经 CLI 写入 Feature + 10 个 AC + implements 边，SPARQL 验证 part_of / implements 边与 narrative 槽齐备；事务中途校验失败时图状态零残留。
- **P-3**：从 prd 模板实例化图骨架后 `finalize`，导出文件结构与文件后端模板实例化结果一致（占位符语义保留）。
- **P-4**：§2 的端到端验收标准整体通过；`docs load` 实体级 / 章节级读取在反转前后返回内容一致；CLI 动词收敛后全部 prompt 资产指引与 CLI 实际命令面零漂移（grep 校验），旧读取入口在别名期内行为不变。
- **P-5**：doc-review 对导出视图的 Layer 1 检查项全部可执行；revision 闭环不产生 md↔KG 漂移。
- **P-6**：`cataforge framework-walkthrough` 在 kg-first authoring 模式下整链路 GO；md-first 存量项目按迁移文档切换后 doctor 全绿。

## 4. 迁移与兼容

- **下游存量项目（md-first 实践）**：默认不强制切换。`context.strategy = kg-first` 项目在 P-4 落地版本升级后，由 framework-update 提示迁移路径：`context ingest`（种子）→ 首次 `context finalize --full-export` 重导出 → 此后 authoring 走图。提供回退开关（保持 md 先行的过渡模式）至少一个 minor 周期。
- **存量 store**：沿用既有重建路径（`kg init --force` → `context ingest`），P-1 落地后追加首次全量导出。
- **doc-only 项目**：完全不受影响（写面策略路由已隔离）。

## 5. 风险与开放问题

1. **导出保真度**：人审版式包含表格、交叉引用目录、分卷结构——P-1 的模板系统需要覆盖全部 doc_type 模板版式，是工作量与回归风险最大的单点；建议以 prd 单 doc_type 先行打通端到端，再横向铺开。
2. **LLM authoring 工效**：一篇 PRD 数十实体逐条 CLI 写入的 token 与往返成本显著高于一次 Edit；P-2 的批量事务（单次调用提交整章）是工效成立的前提，需在 P-4 切换前用 walkthrough 实测对比两种路径的成本。
3. **叙事章节的归属**：§1 概览类纯叙事章节没有实体载体，authoring 落在 Section narrative；"实体正文 vs 节叙事"的边界需要在 P-1 模板中明确（建议：实体定义节由实体正文渲染，非实体节由 Section narrative 渲染）。
4. **混合权威的过渡态**：P-4 切换前 md 权威、切换后图权威，过渡期两种项目并存；reconcile 的权威方向必须由项目配置驱动而非版本驱动，避免升级即翻转。
5. **开放问题**：是否允许 per-doc_type 的权威粒度（如 prd 图权威、test-report 保持 md 权威）？deploy-spec / changelog 等运维类文档是否纳入反转范围？留待 P-1 落地后按实测决策。

## 6. 与既有工作的衔接

本提案的前置数据与管线基底已具备：实体正文进图（narrative_body 上移 SoftwareArtifact）、实体级 title/hash 保真度、实体卡渲染 narrative + part_of、trace 沿 part_of 聚合、repair 的 Section 级闭环、context 写面策略路由、定稿/回灌指引锚点。立项后从 P-1 与 P-2 并行启动。
