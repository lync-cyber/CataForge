# 版本更新与迁移要点 (version-migration)

本文件随包分发给下游项目（scaffold 刷新即滚动到当前版本），是 framework-update 在升级后向用户提示「本次升级更新重点 + 迁移动作」的事实源。下游项目没有 CataForge 的 CHANGELOG.md，`cataforge upgrade check` 的 BREAKING 扫描在下游无输入——本文件是下游唯一的迁移信息通道。

维护规约（框架仓发版时执行，守卫 `scripts/checks/check_migration_notes_version.py` 强制）：

- 每次发版在 `<!-- scriv-insert-here -->` 聚合 CHANGELOG 后，于本文件顶部新增当前版本段：`## [X.Y.Z] — 日期`，含「更新重点」（下游可感知的能力变化，≤6 条）与「迁移要点」（升级后需执行的动作 / 行为变化 / BREAKING 迁移路径；无动作时写一行「无迁移动作」）。
- 滚动窗口：只保留最近 3 个 minor 版本系列，新增段时删除最旧段；完整历史由框架仓 CHANGELOG.md 承担。
- 内容是**提炼**而非复制：只写下游要「做什么 / 注意什么」，不搬运 CHANGELOG 条目原文。

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

## [0.14.0] — 2026-06-23

### 更新重点

- git 卫生命令组：`cataforge git sync` / `git prune` / `git ensure-policy` + SessionStart `git_sync` hook + doctor Git hygiene 报告。
- `PENPOT_MCP_URL` 统一 MCP endpoint 事实源，deploy-time 解析写入各平台 MCP 配置（不依赖平台 `${VAR}` 展开）。
- task-decomp / tech-lead 强制 AC 覆盖被引用的 arch API 契约（契约完整性对账）。
- testing / test-writer 补测试套件性能纪律（慢测分层标签、昂贵 setup 复用）。

### 迁移要点

- `cataforge sync-main` 改为 `cataforge git sync` 的隐藏别名；`--prune-merged` 改为 `--prune-gone`（旧参数保留为隐藏别名）。
- `cataforge penpot mcp-only`（宿主机 npx MCP）已弃用：改用 `penpot remote`（托管）或 `penpot deploy`（自托管）。
- 自托管 penpot-mcp 默认 single-user；需多用户共享设 `PENPOT_MCP_MULTI_USER=true`。旧 compose 被 `penpot doctor` 标记时删除后重新 `penpot deploy` 再生成。
