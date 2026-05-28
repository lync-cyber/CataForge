# 0.5.0 KG-First 迁移指南

> 适用范围：从 0.4.x 升级到 0.5.0 的项目维护者。讲清两件事——KG 模式如何按 doc_type 推进，出问题如何回退。

## 这次迁移在改什么

0.5.0 把 `docs/.doc-index.json` 从权威索引降级为派生缓存，业务文档（PRD / Arch / Test）的实体与跨文档关系改由内嵌 RDF 知识图谱（pyoxigraph + LinkML）承载。Markdown 仍然是人类可读、可 git 追踪的载体，但 KG 是真值；导出回 Markdown 是确定性派生。

**为什么改**：0.4.1 的三层结构缺陷需要从底层解决——LLM 查询效率低（索引漂移时回退到全文解析）、文档腐化（ID 连续性是 WARN 不阻断、内容 hash 漂移要手动 validate）、跨文档关系做成 regex glob 匹配（双向覆盖率假阳、xref 检查假阴）。SPARQL 替代全文解析、SHACL 替代正则前置条件、命名 traceability 谓词（`cf:verifies` / `cf:implements` / `cf:satisfies` / `cf:delivers` / `cf:affects`）替代字符串存在性启发式。

**范围边界**：图层模型业务文档实体（Requirement、Feature、Component、Task、TestCase、Deployment …）。CataForge 自身框架资产（`.cataforge/skills/*/SKILL.md`、`.cataforge/agents/*/AGENT.md`、`.cataforge/rules/*.md`）仍然完全居住在文件系统中——`governance.yaml` 子本体随包发布但 `KGConfig.governance=False` 默认关闭。

## Cutover 模型：全切，不双轨

0.5.0 Alpha 阶段做出的关键决策：**不做双轨期（dual-track），直接 full cutover，粒度是 per-doc_type**。

| 模型选项 | 含义 | 项目选择 |
|---------|------|---------|
| Dual-track | 同一 doc_type 同时维护 Markdown 解析路径 + KG 路径，读路径分流到任一个 | 撤销 |
| Per-doc_type rolling cutover | KG 是 `kg_active_doc_types` 集合内 doc_type 的唯一读路径；集合外 doc_type 仍走 legacy `loader.extract()` | 采用 |

后果：单个 doc_type 切到 KG 之后，该 doc_type 的所有 `loader.extract()` 调用全部走 SPARQL；没有运行时 fallback 兜底。这个权衡换来的收益是——分流逻辑不进每一个调用点，flag gate 只在 dispatch 层判定一次。

风险也由此放大：KG 与 Markdown 的语义偏差直接落到 production 读路径。压制风险靠两件事：

1. **Sub-PR 5 黄金文件回归**——15 个 Group A 调用点每个都跑过 KG-path 输出 vs legacy-path 输出的字节对比，先全绿才允许翻 flag。
2. **`kg_active_doc_types` 粒度**——出问题时移除单个 doc_type 即让该 doc_type 退回 legacy loader，其他 doc_type 不动。

Alpha 范围：`{prd, arch, test}` 三个 doc_type；waterfall 与 agile 双 process_model 均验证。其它 doc_type 在 Alpha / GA 全程留在 legacy loader，是 0.6.0 候选范围。

## 升级前置清单

```bash
# 1. 升级 cataforge 包（带 KG 运行时依赖）
pip install --upgrade "cataforge[kg]"      # 或: uv tool install --upgrade "cataforge[kg]"

# 2. 升级项目脚手架（按平台路由）
cataforge upgrade apply --dry-run
cataforge upgrade apply

# 3. 初始化 KG store（RocksDB-backed Oxigraph）
cataforge kg init                          # 落到 .cataforge/kg/store/
```

`cataforge[kg]` extra 拉 `linkml-runtime>=1.11.1` + `pyoxigraph>=0.5.8`。未装 KG extra 的 CLI 调用 `kg` 子命令时退出码 1 并提示 `pip install cataforge[kg]`。

`cataforge kg init` 在 store 已存在时退出码 1，加 `--force` 强制覆盖。bootstrap 同时把 LinkML `is_a` 链显式物化成 `rdfs:subClassOf` triples 写入 store——pyoxigraph 0.5.x 无 OWL/RDFS 推理，子类闭包查询（`a/rdfs:subClassOf*`）必须依赖这批显式三元组。

## 推进一个 doc_type 到 KG

```bash
# 1. 将业务文档批量导入 KG（六阶段管道：scan → parse → entity → relation → write → verify）
cataforge kg import --doc-type prd
cataforge kg import --doc-type arch
cataforge kg import --doc-type test-report

# 2. 验证 store：orphan + xref-target 完整性
cataforge kg validate

# 3. 跑漂移检测（首次应为 zero divergence）
cataforge kg reconcile

# 4. 把 doc_type 写进 framework.json kg.kg_active_doc_types
```

`framework.json` 片段示例：

```json
{
  "kg": {
    "kg_active_doc_types": ["prd", "arch", "test"]
  }
}
```

读路径切换由 `cataforge.kg._dispatch.is_active_for(doc_type, project_root)` 双层 gate 控制：(a) `doc_type` 在 `kg_active_doc_types` 集合内，且 (b) `.cataforge/kg/store/` 物理存在。任一不成立则透明回退 legacy `loader.extract()` 路径，已部署但未跑 `cataforge kg init` 的项目自动维持 0.4.x 行为。

## doctor 闸口：`kg_ingestion_completeness`

`cataforge doctor` 在 "Docs validation" 之后跑 `kg_ingestion_completeness` gate。

| 状态 | 触发条件 | 退出 |
|------|---------|------|
| SKIP | `.cataforge/kg/store/` 不存在 或 `kg_active_doc_types` 为空 | 不阻断 |
| WARN | KG 中存在 ghost / stale 实体（FS 已删除但 KG 还在） | 不阻断 |
| ERROR | 某 active doc_type 的 Markdown 实体在 KG 中缺失 | 阻断（`failed_count += missing_count`） |

ERROR 严重度直接在 sub-PR 5 合入，无 WARN→ERROR 过渡期。这是 Alpha 退出条件——cutover 落地的同一天 gate 就是硬门。

## 漂移监测：reconcile + compare-read

两条 hot-path 之外的诊断管线，定位不同：

| 命令 | 用途 | 退出语义 |
|------|------|---------|
| `cataforge kg reconcile` | 结构性 diff：FS 实体集 vs KG 实体集对账 | `missing` 或 `ghost` 非空即 exit 1 |
| `cataforge kg compare-read` | 内容性采样：随机取 N 个实体，对比 `content_hash` 是否一致 | 永远 exit 0（仅 diagnostic） |

`reconcile` 跑完写 `docs/.kg-reconcile-report.json`，分 doc_type 列出 `missing_entities` / `ghost_entities` / `missing_relations` / `ghost_relations`。

`compare-read` 三种 alarm 含义：

| Reason | 解读 |
|--------|------|
| `content-hash-mismatch` | FS 已更新但未 re-ingest，KG 内容过期 |
| `kg-missing-entity` | FS 新增了实体，KG 还没有；下一次 `cataforge kg import` 会补 |
| `kg-content-hash-absent` | KG store 损坏（content_hash triple 缺失） |

`compare-read` 不进 doctor gate，因为它是 sampling 性质——alarm 在阈值之下的偶发不应阻塞写。alarm 持续才触发"该 doc_type 移出 `kg_active_doc_types`"的运维动作。

## 推进与撤回 doc_type 的判定

**推进进入 `kg_active_doc_types` 的条件（三条全部满足）**：

1. `cataforge kg reconcile --doc-type <name>` 报告 `missing` / `ghost` 均为 0。
2. Group A 调用点的黄金文件回归测试在该 doc_type 上通过（sub-PR 5 已通过即满足，无新增黄金的情况下不需要每次重跑）。
3. `cataforge kg compare-read --doc-type <name>` 在项目实际内容上的采样轮次 0 alarm。

**撤回出 `kg_active_doc_types` 的条件（任一触发即应撤回）**：

1. `cataforge kg reconcile` 报告该 doc_type 有 `missing` / `ghost`，且连续两次 `cataforge kg repair` 仍未消除。
2. `cataforge kg compare-read` 该 doc_type 在 10 轮连续采样中累计 ≥2 次 alarm。
3. 任一 Agent 在该 doc_type 上产生语义错误的输出，定位到 KG 读路径。

撤回操作仅需编辑 `framework.json` `kg.kg_active_doc_types` 移除该 doc_type；该 doc_type 的下一次读立即走回 legacy loader，其余 doc_type 不动。Store 中的旧三元组保留——下一次重新推进时 `cataforge kg import` 会按 content-hash dedup 跳过未变更实体。

## 回滚

回滚分两级。优先用第一级；只在 store 整体损坏到 reconcile 都无法 diff 时升级到第二级。

### 一级：单 doc_type 回滚（首选）

适用：某一个 doc_type 出现语义偏差或漂移持续不消。

```bash
# 在 framework.json 移除该 doc_type
# kg.kg_active_doc_types: ["prd", "arch", "test"]  → ["arch", "test"]
```

效果：该 doc_type 的所有读路径下次起走 legacy `loader.extract()`；其它 doc_type 不动；KG store 不动。Agent 的下一次 dispatch 会自动按新 config 路由。

### 二级：systemic snapshot 回滚

适用：pyoxigraph store 损坏、整个 KG 索引不可信、需要回到 ingest 前的洁净状态。

**前置**：在 ingest 前已经跑过 `cataforge kg snapshot --output <path>` 落过快照。**没有快照就没有回滚**——这是 KG-first 模型的硬约束。

```bash
# 1. 停止所有跑着的 cataforge 后台进程 / agent 调度
# 2. 验证快照完整性
cataforge kg snapshot --verify <snapshot.nq>

# 3. 移除当前 store
rm -rf .cataforge/kg/store/

# 4. 从快照恢复
cataforge kg rollback <snapshot.nq>

# 5. 回滚后校验
cataforge kg validate
cataforge kg reconcile
cataforge doctor
```

快照路径建议：`.cataforge/backups/kg-pre-{action}-{YYYYMMDDTHHMMSSZ}.nq`。CataForge 不自动清理快照，operator 自行管理保留策略。

### 不可回滚情形与人工兜底

如果出现以下情形——快照丢失 + store 损坏 + Markdown 也已被 KG export 覆盖——KG 工具链无法自动恢复。人工兜底路径：

1. `git checkout <pre-migration-tag> -- docs/` 把 Markdown 拉回迁移前状态。
2. `rm -rf .cataforge/kg/store/`。
3. `framework.json` 的 `kg.kg_active_doc_types` 清空。
4. 重跑 `cataforge kg init` + `cataforge kg import` 重建 store。
5. 跑完整 doctor + reconcile 验证。

这条路径假设 docs/ 在迁移前有干净的 git tag——这是 0.5.0 升级清单的隐含前提，建议升级前显式打 tag（`git tag pre-kg-cutover-0.5.0`）。

## 已知边界与未来工作

下列项不阻塞 Alpha 落地，但 operator 应知悉：

| 项 | 状态 | 处置 |
|---|------|------|
| 仅 `{prd, arch, test}` 三个 doc_type 在 KG 路径上 | Alpha 范围 | 其它 doc_type 在 0.6.0+ 评估扩展 |
| SHACL `sh:closed true` 运行期校验 | 接口已留（`--shacl` flag），pyoxigraph↔rdflib 桥未实现 | schema-level write-time 检查兜底；GA 重审 |
| 自然语言查询 LLM 接口 | 0.6.0+ 候选 | 现有 `QueryAPI` / `TraceAPI` 提供编程接口 |
| `cataforge kg compare-read` 是 diagnostic 而非 gate | 设计选择 | alarm 持续才触发运维动作；不进 CI 闸口 |
| Component C-NNN ↔ UIComponent UC-NNN 重映射 | `cataforge kg import` 自动 codemod | 重命名后 ui-spec 的 inbound xref 自动追踪 |
| `docs/.doc-index.json` 不再权威 | 派生缓存 | 第三方直接 import 该 JSON 会读到过期数据；改用 `cataforge kg query` |

## 参考

- 设计提案：[docs/proposals/kg-migration-0.5.0/README.md](../proposals/kg-migration-0.5.0/README.md)
- Cutover 完整规约：[task-7-rollout-strategy.md §7.5](../proposals/kg-migration-0.5.0/task-7-rollout-strategy.md)
- 验证行为参考：[docs/reference/kg-verified-behaviors.md](../reference/kg-verified-behaviors.md)
- CLI 命令参考：[docs/reference/cli.md](../reference/cli.md)（`kg` 段）
