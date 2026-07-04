# 提案：移除 context.mode=hybrid —— 收敛为 graph（默认 kg-first）/ markdown（无 KG）两态

> 状态：已实施。context.mode 收敛为 graph（默认 kg-first）/ markdown（无 KG opt-out）两态，hybrid 已从核心分派 / 授权策略 / 写入门 / scaffold / schema / doctor / setup Choice / reconcile 全面移除，存量 hybrid 于 upgrade 自动迁移→graph。以代码为准，本文余下为历史设计记录。
> 范围：`context.mode` 枚举从三态收敛为两态，删除 `hybrid`；牵涉核心分派 / 授权策略 / 写入门 / scaffold / schema / doctor / upgrade / reconcile + 测试 + 受影响提案。
> 证据源：下游 #373.1（hybrid 下任务状态无合规落盘）+ #379/#384（finalize 塌卷 / write-doc 关系污染 / amendment 错卷——均在 KG↔markdown 来回操作中爆发）。
> 关系：**取代** `context-kg-subsystem-remediation.md` 的「hybrid 为建议默认」决策；**重新激活** `kg-first-authoring-inversion.md` 的「图为唯一事实源、markdown 为导出审查视图」愿景。

---

## 0. 一句话

`hybrid`（markdown 权威 + 派生 KG）逼 agent 在「读/门禁走 KG、授权走 markdown」之间来回切换，每次切换都要 reconcile 对账，是 #373.1 / #379 / #384 一系列下游错的共同温床；其声称的「KG 门禁但授权留 markdown」收益被 thrashing 吃光。**删 hybrid，收敛为 graph（默认 kg-first）/ markdown（无 KG opt-out）两态。**

## 1. 为什么删 hybrid

kg-first 的事实源应当唯一。hybrid 让 markdown 成为「设计推进时被授权依赖的产物」，而 markdown 在 kg-first 下本应只是导出给人审查的副本：

- **双写来回**：实体/关系/覆盖门禁读 KG，但授权写 markdown 再 ingest 回灌——每个收口点一次三方哈希对账，窗口里任何中间态都可能漂移。
- **错误温床**：`context write` 在 hybrid 被设计性拒绝（#373.1）；finalize 在 graph/hybrid 切换时塌拆卷（#384）；多次 write-doc 关系交叉污染（#379）；amendment 落错卷。这些在 hybrid 下能「退回 markdown 编辑」临时规避，掩盖了根本不一致。
- **收益微小**：「低成本 markdown 授权 + KG 门禁」听似两全，实则两套权威并存的复杂度远超其省下的 token。

## 2. 两态目标模型

| 模式 | KG | markdown | 授权面 | 门禁 |
|---|---|---|---|---|
| **graph**（默认，kg-first） | SSOT | 导出的人审视图（finalize） | `context write/update` 直写图 | KG 驱动（覆盖/追溯/read） |
| **markdown**（opt-out，无 KG） | 无 | 唯一事实源 | 直接编辑 docs/ | 文件/索引降级路径 |

- `DEFAULT_MODE = "graph"`，`MODES = {markdown, graph}`。
- `ModePolicy` 大幅简化：`graph_enabled == graph_is_source == graph_authoring_allowed == (mode=="graph")`；markdown 三者皆假。`remediation_for` 只剩 graph（export/ingest/manual）与 markdown（ingest）两支。

## 3. #373.1 如何溶解

- **graph**：`cataforge context update <task> --slot task_status=done` 直写 KG 实体 slot，本就合法。tdd-engine §Step 5.4 无需改。
- **markdown**：无 KG，任务状态就是 dev-plan §1 Sprint 表「状态」列（文档事实源），Step 5.4 走文档编辑。
- 「三分裂」中那条「hybrid 既要写 KG 又被拒」的矛盾消失；不再需要 mode-aware 状态入口。Step 5.4 仅需按两态分别表述（graph 写实体 / markdown 改 §1 行），无中间态。

## 4. 代码足迹（改动清单）

排除：`workflow-framework-generator` 的 `type: hybrid`（workflow 类型域词，与 context.mode 无关）。

**src/**（约 13 文件）：
- `domain/kg/_dispatch.py`：`MODES` 去 hybrid、`DEFAULT_MODE="graph"`；`kg_enabled` 语义随之（仅 markdown 无 KG）。
- `domain/kg/authority.py`：`ModePolicy` 三属性合一；`remediation_for` 去 hybrid 分支。
- `application/context/write.py`（11 处）：`_require_graph_mode` 去 hybrid 分支（只剩 graph 通过 / markdown 拒并指向「编辑 docs/」）；相关 ModeError 文案。
- `application/context/router.py` / `domain/kg/reconcile.py`：去 hybrid 分支。
- `interface/cli/setup_cmd.py`(6) / `bootstrap_cmd.py`(4) / `context_cmd.py`(2) / `doctor/context_authority.py`(3)：默认值、提示、有效性校验。
- `core/schema/framework.py`(2) + `domain/kg/_generated/core_pydantic.py`：`mode` 默认与枚举（_generated 经 codegen 再生）。
- `core/scaffold.py`(2) + `core/types.py`：见 §5 迁移。

**tests/**（约 16 文件）：hybrid 专属用例删除或重表述——`test_context_mode.py`、`test_authority_policy.py`、`test_write.py`（graph-door-rejected-in-hybrid → 改为 markdown 拒）、`test_finalize_authoring_routing.py`、`test_ensure_store.py`、`test_router.py`、`test_reconcile_triage.py`、`test_setup_context_mode.py`、`test_bootstrap_cmd.py`、`test_scaffold.py`、`test_doctor_context_authority.py` 等。

**资产/文档**：`.cataforge/framework.json`（本仓 mode）、`schema framework.json.tmpl`、`ORCHESTRATOR-PROTOCOLS.md`（hybrid 提及）、本仓 `.cataforge/.gitignore` 注释；取代 remediation 提案的 hybrid-默认决策。

## 5. 迁移：hybrid → graph 自动

`scaffold._migrate_context_mode` + `upgrade`：

- 旧 `context.mode=hybrid`（含「缺失 mode」回退到旧默认 hybrid 的项目）在 `cataforge upgrade apply` 时**自动迁移到 graph**：种子 `context ingest`（md→KG）→ 首次 `context finalize`（KG→md 全量导出）→ 写 `context.mode=graph`。
- 旧双轴推导：`doc-only→markdown`、`kg-first×*→graph`（不再产出 hybrid）。
- 迁移须幂等、可被 `cataforge doctor` 校验；迁移后 reconcile 归零方算成功，否则报阻塞点而非静默放行。

## 6. 前置/风险：graph 模式加固（必须正视）

删 hybrid = graph 成为承载 KG 门禁的唯一模式，下游再无「退回 markdown 编辑」的逃生口。故 graph 现存摩擦从「可绕」升为「必须硬」：

- finalize 在拆卷文档上保卷结构、不塌单卷（#384 信号）。
- amendment 子代理精确定位目标分卷、不波及主卷（#379 信号）。
- 多次 write-doc 按 doc-id 原子替换关系边、不累积陈旧/交叉污染（#379 信号）。
- approved 冻结文档 status 降级有守卫。

**建议**：hybrid 移除与上述 graph 加固成对推进——加固先行或同 PR 内随附回归测试，避免「默认即踩雷」。

## 7. 取代与重新激活

- **取代**：`context-kg-subsystem-remediation.md` §「默认 hybrid」决策（其 ModePolicy / document_pipeline / 三方哈希 triage 等原语**保留复用**，仅枚举从三态降两态）。
- **重新激活**：`kg-first-authoring-inversion.md` 的核心愿景（图为唯一事实源、markdown 为导出视图）——在新模型里即「graph 为默认」，无「过渡默认」中间态。

## 8. 验收标准

- `MODES == {markdown, graph}`，`DEFAULT_MODE=="graph"`；全仓 hybrid 引用清零（除 workflow `type` 域词）。
- 默认 graph 项目整链路（bootstrap→authoring→doc-review→finalize→reconcile）GO；markdown 项目 docs-only 链路 GO。
- 存量 hybrid 项目 `upgrade apply` 自动迁移 graph，reconcile 归零、doctor 全绿；迁移幂等。
- graph 加固回归（finalize 保卷 / amendment 定位 / write-doc 关系幂等）有测试守。
- `framework-walkthrough` 在 graph 与 markdown 两模式 GO。
