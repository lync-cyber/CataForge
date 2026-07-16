# 版本更新与迁移要点 (version-migration)

本文件随包分发给下游项目（scaffold 刷新即滚动到当前版本），是 framework-update 在升级后向用户提示「本次升级更新重点 + 迁移动作」的事实源。下游项目没有 CataForge 的 CHANGELOG.md，`cataforge upgrade check` 的 BREAKING 扫描在下游无输入——本文件是下游唯一的迁移信息通道。

维护规约（框架仓发版时执行，守卫 `scripts/checks/check_migration_notes_version.py` 强制）：

- 每次发版在 `<!-- scriv-insert-here -->` 聚合 CHANGELOG 后，于本文件顶部新增当前版本段：`## [X.Y.Z] — 日期`，含「更新重点」（下游可感知的能力变化，≤6 条）与「迁移要点」（升级后需执行的动作 / 行为变化 / BREAKING 迁移路径；无动作时写一行「无迁移动作」）。
- 滚动窗口：只保留最近 3 个 minor 版本系列，新增段时删除最旧段；完整历史由框架仓 CHANGELOG.md 承担。
- 内容是**提炼**而非复制：只写下游要「做什么 / 注意什么」，不搬运 CHANGELOG 条目原文。

## [0.18.0] — 2026-07-16

### 更新重点

- 多平台部署状态模型：`framework.json` `deployment.targets` 可声明 claude-code / cursor / codex / opencode 多平台，每平台独立部署记录与锁；`cataforge deploy --platform` / `doctor --platform` 按平台隔离操作。
- `pip install cataforge` 开箱即败已修复：wheel 运行时依赖剥离 `linkml-runtime → prefixcommons → pytest-logging` 传递链，pip 消费者不再在 Debian/Ubuntu 系统 setuptools 上构建崩溃。
- KG 文档 id 契约修复：ingest 按 canonical frontmatter `id` 解析，多份同 doc_type 文件不再折叠为同一 Document；整篇 authoring 原子替换旧结构、失败补偿快照恢复、hash 不变的实体归属仍随新抽取同步。
- viz dashboard UI/UX + 无障碍大修：键盘可达 / ARIA 语义 / 色盲安全板 / `prefers-color-scheme` 暗色主题；catalogue 视图新增邻域聚焦浏览器（大图按需展开）。
- 无人值守流静默存活监督：`cataforge unattended build` 增量落盘 + stream-silence liveness 击杀挂死会话，新增 `--iter-timeout` / `--silence-timeout` 参数。
- 可选 design-grill 工作流：UI 设计定稿前对抗式多轮质询逼出缺陷（默认不激活，须显式调用）。

### 迁移要点

- 用 `pip install cataforge` 的下游现开箱可用，此前的 `--use-pep517` workaround 不再需要。
- **graph 模式项目行为更严格**：文档 id 碰撞现在显式 FAIL（此前静默折叠为同一节点）。升级后跑一次 `cataforge context reconcile` 与 `cataforge doctor` 复核；历史上被折叠的文档需确保各自 frontmatter `id` 唯一后重新 ingest。
- 多平台部署为选择加入：单平台项目无需改动（向后兼容）；需要多平台时在 `framework.json` `deployment.targets` 声明目标，再按 `--platform` 部署。
- 无人值守 `unattended build`：`UNATTENDED_LOOP_ITER_TIMEOUT_SEC` 语义改为总时长宽松背板（默认 10800s），挂死判活改由 `UNATTENDED_SILENCE_TIMEOUT_SEC`（默认 900s）驱动。
- 无其他 BREAKING。

## [0.17.0] — 2026-07-07

### 更新重点

- KG 本体开放有界 `DomainEntity` 逃生阀：下游可在 `framework.json` `kg.custom_entity_prefixes` 注册自定义前缀（如 `ORD-001`），落图为可查询、可追溯的领域实体，无需改框架源码。
- 拆卷（split-volume）机制整体废除：一个逻辑文档 = 一个评审文件，不再拆分为多个物理分卷。
- 产文档角色卡（product-manager / architect / ui-designer / tech-lead / qa-engineer / devops）改为 kg-first authoring 契约：经 `context write-doc`/`write-narrative`/`transact` 落稿 + `finalize` 导出人审视图。
- viz 大幅增强：inspector 详情面板、omnibox 全局检索、图⇄表双模、按层折叠、KPI 历史快照（`viz snapshot`）与多项目聚合（`viz portfolio`）、暗色主题。
- doc-review checker 批量误报/漏报修复：`check_xref` 补纯 §-ref 章节存在性校验、dev-plan KG 覆盖门真空态回退、test-report 表格解析、占位符守卫误伤集合字面量。
- `context write` / `transact add_entity` 对已被文档覆盖的实体写入显式拒绝并指路正确入口，消除此前的静默不落地。

### 迁移要点

- **BREAKING（拆卷废除）**：若曾用 `--volume-type` CLI 参数、`-s{N}.md` 分卷产出、或文档 frontmatter `volume`/`split_from` 字段，均已移除。超长文档改为按 Layer 1 建议拆分为多个独立逻辑文档，而非物理分卷；升级后重新生成受影响文档。
- graph 模式项目对已被 Document 覆盖的实体直接 `context write` / `transact add_entity` 会被拒绝：改用 `write-narrative`（重写叙事）/ `update`（slot 就地合并）/ `write-doc`（整篇重着陆）。
- doc-review 检查器修复后行为更严格（如 §-ref 现真实校验章节存在），此前被误报掩盖的真实问题可能在升级后首次暴露；建议升级后跑一次 `cataforge skill run doc-review -- all` 复核。
- 需要自定义领域实体前缀的项目在 `framework.json` `kg.custom_entity_prefixes` 注册 `{prefix: domain_type}`；非法前缀格式（须 `^[A-Z]+$`）注册时即报错。
- 无其他 BREAKING。

## [0.16.0] — 2026-07-05

### 更新重点

- code-review 静态检查扩容：架构分层守护（`arch.yaml` 声明方向矩阵即激活）、复杂度门禁（`complexity.yaml` 四指标阈值 + 棘轮基线）、`api_surface` / `config_dead_key` / `pragma_inventory` 探针、`--format json` 机读输出。
- 新增 feature-walkthrough skill：对交付项目功能实现做验收式动态走查，报告落 `docs/reviews/walkthrough/`。
- 无人值守构建循环：`cataforge unattended build <sprint>` 对已冻结 sprint 每轮 fresh-context 驱动，双层 deny hook + fail-closed preflight 护栏。
- viz 增强：`viz overview` 项目健康 KPI、dashboard KPI strip / tab 分组 / 跨视图跳转、`viz assets` 资产目录面板。
- context 增强：`finalize --doc-type / --dry-run`；reconcile 检测节内嵌切片失同步；doc-review 新增导出新鲜度 Layer 1 门禁。

### 迁移要点

- 无 BREAKING。升级后跑 `cataforge doctor`；若历史上有旁路写入 EVENT-LOG，按提示跑 `cataforge event accept-legacy` 设水位线。
- 架构分层守护与复杂度门禁默认**不激活**：需在项目 `arch.yaml` / `complexity.yaml` 写入声明（comment-only 模板视为未声明）。
- graph 模式项目若 doc-review 报导出陈旧 FAIL：先 `cataforge context finalize` 重导出再复审。
- `.cataforge/baselines/*.json` 变更须伴随 CODE-SCAN 报告变更，否则 framework-review 防篡改对账 FAIL。
