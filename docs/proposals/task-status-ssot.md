# 提案：任务状态单一事实源 —— 收敛三分裂表示，去除 Step 5.4 的模式失配

> 状态：draft（根因已定位，修法方向待裁定）。
> 范围：dev-plan 任务生命周期状态（todo / in_progress / blocked / review / done）的**落盘权威**与**写入路径**；牵涉 tdd-engine §Step 5.4、dev-plan 模板、KG `cf:task_status` slot 的 ingest/export、sprint-review Layer 1 与 sprint 完成触发器。
> 证据源：下游 issue #373.1（Ink-Source standard Phase5，context.mode=hybrid 实测「任务 done 状态无任何协议合规的持久化路径」）。
> 关系：本提案**不修改** `context-kg-subsystem-remediation.md` 已定的 `context.mode` 三态模型与「hybrid 为默认」决策；它修复的是**任务状态这一具体事实**在三态下的表示一致性。

---

## 0. 一句话

任务状态在框架里有**三个互不连通的表示**，且 tdd-engine §Step 5.4 指向其中一条在默认 `hybrid` 模式下被设计性拒绝的路径。修法不是绕过 hybrid，而是**把任务状态收敛为单一事实源、让 Step 5.4 经一个不分支后端的入口写入**。

## 1. 现象

下游 `standard` 流程、默认 `context.mode=hybrid`：任务完成时按 tdd-engine §Step 5.4「通过 `cataforge context write` 将 dev-plan 任务实体 status slot 更新为 done」执行，被拒：

```
authors directly into the knowledge graph, which is canonical only under
context.mode = "graph". This project is "hybrid" (Markdown is canonical) —
edit the documents under docs/ and run `cataforge context ingest`, or
switch context.mode to graph.
```

而任务卡 markdown 又无 status 字段可改 → 「edit md + ingest」也无字段可落。结果：hybrid 下任务 done 状态**无任何协议合规的持久化路径**，orchestrator 被迫退回 EVENT-LOG / 项目指令文件追踪（审计流被误用为状态权威）。

## 2. 根因：状态表示三分裂

| # | 表示 | 位置 | 谁读它 | 模板是否产出 |
|---|------|------|--------|------------|
| (a) | §1 Sprint 总览表「状态」列 | dev-plan 文档 | `sprint_review` Layer 1（`_TASK_TABLE_RE`）+ ORCHESTRATOR §Sprint Review 完成触发器 | **是**（`standard/dev-plan.md` §1） |
| (b) | 任务卡 `- Status:` bullet | dev-plan 文档 | KG ingest（`entity_extract._STATUS_RE` → `cf:task_status`） | **否**（任务卡模板无此字段） |
| (c) | KG 实体 `cf:task_status` slot | 图 store | `context write/update`（graph 写）+ export 回灌 (b) | 由 (b) ingest 而来 |

致命断点：

- **(b) 模板缺字段** → KG 在 hybrid 下从 (b) 抽不到状态，(c) 恒空。
- **Step 5.4 指 (c) 的直写** → 在 hybrid 被 `_require_graph_mode` 设计性拒绝（直写图会被下次 md→KG sync 覆盖）。
- **真正驱动「Sprint 完成」判定的是 (a)** → 与 (b)/(c) 完全不连通。

即：Step 5.4 写的是 (c)，KG 想从 (b) 读，门禁却认 (a)，而模板只产出 (a)。三者各行其是。这不是 hybrid 的缺陷——是任务状态**没有单一权威表示**，叠加 Step 5.4 指了一条 hybrid 下不通的路。

## 3. 为什么不是「删 hybrid」

`context-kg-subsystem-remediation.md`（已取代旧 kg-first-inversion 配置模型）明确把 `hybrid` 定为**刻意的默认**，非过渡态：

- 「默认 `hybrid`：既保住 KG 驱动的覆盖/追溯门禁默认可用，又让 markdown 仍是低 token、人友好的授权底料；`graph` 成为显式 opt-in」。
- 旧模型里真正「过渡」的 `strategy × authoring` 正交轴 + `authoring=md 过渡默认`**已被移除**，因其正交性本身是腐化根源。
- `test_graph_door_rejected_in_hybrid_mode`：hybrid 下 `context write` **应当**清晰报错，是设计验收项——§1 现象里的报错是预期行为，不是回归。

故删 hybrid 会丢掉「要 KG 门禁但授权留在低成本 markdown」这一不可替代档；下游反复报错的真因是**协议指令与状态表示没尊重 hybrid 默认**。

## 4. 修法选项（均保留 hybrid 默认；差别在状态权威落点与写入机制）

### 选项·文档为权威（§1 表为 SSOT）

- §1 Sprint 表「状态」列定为唯一 SSOT（它已是 `sprint_review` + 完成触发器 + 模板的事实源）。
- Step 5.4 改为更新 §1 表对应行的状态列（文档事实，hybrid 下天然合规），由现有 reconcile/ingest 回流 KG。
- 删任务卡 `- Status:` ingest 路径（(b)），或令 KG `cf:task_status` 从 §1 表行 ingest，使 (c) 成为 (a) 的派生。
- **代价**：纯协议 + 模板/ingest 层；不碰 graph 授权代码。**风险**：graph 模式下 §1 表是导出视图，写入须经实体——需确认 graph 下「改 §1 行」语义等价于「写实体 slot 后导出」。

### 选项·框架做模式无关的状态入口

- 新增/改造一个 mode-agnostic 状态更新能力（如 `cataforge context set-status <task> done`）：`graph` 走实体 slot 直写；`hybrid`/`markdown` 走文档（§1 行）编辑 + ingest。
- Step 5.4 调这一个命令，**调用方不分支后端**——契合 COMMON-RULES「后端由框架按 context.mode 路由」I/O 契约。
- **代价**：改 `application/context/write.py` + 新 CLI 子命令 + 测试（hybrid/graph 双路）。**收益**：最贴 I/O 契约，状态写入彻底去模式化，根除同类失配。

### 选项·改默认为 graph（否决）

- 若默认 `graph`，则 `context write` 状态 slot 本就合法、Step 5.4 不变。
- **否决理由**：与 remediation 提案「hybrid 为默认、graph 为显式 opt-in」决策直接冲突；且 graph 模式有自身下游摩擦（finalize 塌卷、relation 交叉污染，见 #379/#384 信号）。不应为单点状态写入反转全局默认。

## 5. 验收标准

- 默认 `hybrid` 项目：任务完成后状态 done 有协议合规落盘路径，无需退回 EVENT-LOG / 项目指令文件作权威。
- `sprint_review` Layer 1 与 §Sprint Review 完成触发器读到的状态，与任务实际完成态一致（不再依赖 #393 的 `task_status_external` 兜底来掩盖缺口）。
- `graph` 项目：同一 Step 5.4 路径不报错、状态落入 KG 实体 slot。
- 状态表示数量从 3 收敛到 1 权威 + 至多 1 派生；`cataforge doctor` / reconcile 不因状态表示分裂产生漂移。

## 6. 关联

- 已落地互补项：#393（sprint-review Layer 1 自动检测外部状态追踪 + representative deliverables）——缓解了「无 status 列致全任务噪声」的**症状**，本提案修**病根**。
- #378.1（sprint_check 解析无 status 列总览表 + 区间卷）：与本提案同属「状态在 dev-plan 的可解析表示」主题，可联动定 §1 表结构。
