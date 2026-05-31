# CataForge 框架审查与演进 · 2026-05

本目录是一轮「实现审查 + 跨平台部署评估 + 新增走查能力 + 产品演进策略」综合任务的可提交交付物集合。采用**多智能体动态工作流**完成：fan-out 并行发现 → 对抗性验证 → 综合落盘。

## 交付物索引

| # | 交付物 | 文件 |
|---|--------|------|
| 1 | 实现审查报告（分类 findings + 修复方向） | [`01-implementation-review.md`](01-implementation-review.md) |
| 2 | 跨平台部署评估（四端矩阵 + 缺口 + 改进路径） | [`02-platform-deployment-eval.md`](02-platform-deployment-eval.md) |
| 3 | 项目走查 skill 首次运行报告（改进建议初稿） | [`03-walkthrough-first-run.md`](03-walkthrough-first-run.md) |
| 4 | 产品演进策略备忘（盘点 + 前瞻 + 4a/4b 评估矩阵） | [`04-evolution-strategy.md`](04-evolution-strategy.md) |

配套新增能力：`framework-walkthrough` skill 本体落在 [`.cataforge/skills/framework-walkthrough/`](../../../.cataforge/skills/framework-walkthrough/SKILL.md)（SKILL.md + 3 个 references）。

## 本分支已落地的修复（非纯报告）

除四份报告与新 skill 外，本分支还落地了两处审查过程中确认的真实缺陷修复：

- **全局 `--project-dir` 透传**（对应走查 R-S2）：新增 [`helpers.root_relative_default`](../../../src/cataforge/interface/cli/helpers.py)，让 `docs`（index/load/validate/migrate-*）与 `kg`（store/ingest/query 共 13 个）子命令的本地 `--project-root` / `--db-path` 在缺省时回退到全局 `--project-dir`（显式 local 仍优先；未设 `--project-dir` 时行为不变）。修复前 `cataforge --project-dir <X> kg init` / `docs index` 会忽略该 flag 写到 cwd 发现的项目。附回归测试 [`test_project_dir_kg_docs.py`](../../../tests/cli/test_project_dir_kg_docs.py)（3 passed）。
- **`framework-review` B2 孤儿白名单**：把新增的 `framework-walkthrough` 加入 `ORPHAN_SKILL_WHITELIST`，与其他按需触发的 infra skill 对齐，使 `framework-review -- skills` 对它 0 WARN。

其余报告内的 findings（R-001~R-026、四端缺口、4a/4b）均为**建议**，未在本分支实施，留作后续按优先级排期。

## 方法学

1. **Phase 0 · 校准**：抽样复核任务书的架构断言是否仍成立（仓库迭代快），修正偏差，标注已确认/已驳回的锚点。
2. **Phase 1 · 并行发现**：四条独立流 fan-out——实现审查（11 路子系统 + 元工具盲区）/ 平台评估（四端 + 跨平台矩阵 + 部署机制）/ 走查 skill（建造 + 端到端跑通）/ 演进策略（盘点 + 4a + 4b + 前瞻）。
3. **Phase 2 · 对抗性验证**：每条候选 finding 交独立怀疑者复核（是否真实 / 可复现 / 是否已被现有机制缓解），证据对不上即驳回，剔除误报。
4. **Phase 3 · 综合**：跨流去重、按 severity / 用户价值排序（不含工时估算，用成本/复杂度维度），按 COMMON-RULES 分类体系落盘。

分类与归因沿用 COMMON-RULES §统一问题分类体系 / §归因分类 / §三态判定逻辑；severity ∈ {CRITICAL, HIGH, MEDIUM, LOW}。

## Phase 0 校准记录

抽样复核结论（任务书数据 vs 实测）：

| 任务书断言 | 实测 | 处置 |
|-----------|------|------|
| tests/ 175 文件 | **215** 文件 | 以实测为准 |
| 30 个 skill | **27**（含新增 framework-walkthrough；原 26）| doc-gen/doc-nav/doc-review 等已合并入统一 `context` skill |
| 6 个 Python 内置 skill | **8 个**（另含 `doc_consistency`、`testing`）| 双轨面更宽，纳入审查 |
| ~12 个空残留顶层包目录 | git **零跟踪**（仅本地 `__pycache__`，已 ignore）| **驳回**：不构成仓库腐化 |
| `mc-0.1.5` 死守卫 | 路径迁走 + `allow_missing:true` → 永远静默通过 | **确认**：真 finding（详见交付物 1） |
| `lifecycle.py`/`helpers.py`/`feedback_cmd.py` 偏大 | 617 / 560 / 558 LOC，但 `ruff C901` 全绿 | 议题是模块体积/内聚，**非**圈复杂度门违规——据此校准 severity |

两处「看似缺陷实为本地产物」已被对抗性验证拦下，特此记录以示纪律：

- **空残留目录**：`git ls-files` 证实 12 个旧顶层包目录零跟踪、`__pycache__` 已 gitignore；git 不跟踪空目录，故对仓库不构成腐化（仅本地构建残留）。
- **部署漂移**：本地 `.claude/`（运行会话所见）仍显示 `doc-gen`/`doc-nav` 旧 skill 名，但**源** `.cataforge/rules/` 与 `agents/` 已无悬挂引用——这是本地未重新 deploy 的陈旧，**非**已提交的仓库缺陷（`.claude/` 本就 gitignored）。其引申（部署产物可静默滞后于源，无自动重部署）作为一条平台/机制议题纳入交付物 2。

## 落盘位置说明

任务书建议把审查报告放 `docs/reviews/framework/`，但该目录在本仓 **gitignored**（dogfood 运行产物目录，不入版本控制）。为使交付物可提交、可评审，全部落到 **`docs/proposals/`**（tracked，沿用本目录既有的纯 markdown、无 front-matter 约定）。`framework-walkthrough` skill 的**运行时**输出仍正确指向 `docs/reviews/framework/`；交付物 3 是其首次运行的可提交副本。
