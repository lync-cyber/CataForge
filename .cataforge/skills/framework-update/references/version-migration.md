# 版本更新与迁移要点 (version-migration)

本文件随包分发给下游项目（scaffold 刷新即滚动到当前版本），是 framework-update 在升级后向用户提示「本次升级更新重点 + 迁移动作」的事实源。下游项目没有 CataForge 的 CHANGELOG.md，`cataforge upgrade check` 的 BREAKING 扫描在下游无输入——本文件是下游唯一的迁移信息通道。

维护规约（框架仓发版时执行，守卫 `scripts/checks/check_migration_notes_version.py` 强制）：

- 每次发版在 `<!-- scriv-insert-here -->` 聚合 CHANGELOG 后，于本文件顶部新增当前版本段：`## [X.Y.Z] — 日期`，含「更新重点」（下游可感知的能力变化，≤6 条）与「迁移要点」（升级后需执行的动作 / 行为变化 / BREAKING 迁移路径；无动作时写一行「无迁移动作」）。
- 滚动窗口：只保留最近 3 个 minor 版本系列，新增段时删除最旧段；完整历史由框架仓 CHANGELOG.md 承担。
- 内容是**提炼**而非复制：只写下游要「做什么 / 注意什么」，不搬运 CHANGELOG 条目原文。

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

## [0.15.0] — 2026-06-28

### 更新重点

- deploy 注入平台 `settings_defaults`（set-if-absent）：Windows 上为 Claude Code 落 Git Bash 偏好；doctor 新增 Shell preference 检查。
- viz 接入 agentic 工作流：新增 project-visualization 发现型 skill，Sprint 收口确定性产出 `docs/viz/dashboard.html`。
- Penpot 集成收敛为单一 penpot-bridge skill（read / sync / generate / verify），并接入视觉 grounding（`export_shape` 渲染像素）。
- `context.mode` 收敛为 graph / markdown 两态。
- 续接（continuation）固定为 file-based 重派发，不依赖平台原生续接原语。
- code-review 新增 Layer 1 UI 保真检查（`ui_fidelity`）与 visual-fidelity 审查维度。

### 迁移要点

- penpot-sync / penpot-implement / penpot-review 三个 skill 已移除：改用 penpot-bridge 的对应操作。
- `context.mode: hybrid` 不再有效：改为 `graph` 或 `markdown`。
- Windows 项目 deploy 后 `.claude/settings.json` 被注入 Git Bash 偏好（用户手动设过的值不覆盖）；机器无 Git Bash 时 doctor 给 WARN。
- graph 模式项目确认 `.gitignore` 未忽略 `.cataforge/kg/snapshots/`，否则图谱唯一持久化产物会静默丢失（doctor 已加检查）。
