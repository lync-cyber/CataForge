### Added

- **`cataforge sync-main`** —— 单命令把本地默认分支从 `origin` 快进到最新；`--prune-merged` 删除已合并的 feature 分支。拒绝在工作区脏 / 分叉 / detached HEAD 时执行任何写动作。`prepare-pr.sh` 的 cheat sheet 也一并指向这条命令。
- **`cataforge claude-md`** —— `check` 子命令对照 `framework.json#claude_md_limits` 校验 CLAUDE.md 大小、§项目状态 行数、Learnings Registry 条目数；`compact` 子命令把超限的 Learnings Registry 旧条目归档到 `.cataforge/learnings/registry-archive.md`。同一组阈值由 `cataforge doctor` 复用。
- **`cataforge issue triage`** + 配套 **framework-issue-triage skill** —— 上游 maintainer 侧从 `gh issue list` 拉 open issue，Layer 1 解析 `cataforge --version` / `framework-review FAIL` / `upstream-gap` 字段，分类 `confirmed` / `already-fixed` / `needs-repro` / `unrelated`，把 `confirmed` 写成 `docs/reviews/triage/SKILL-IMPROVE-<id>-issue-<N>.md` 草稿。闭环 framework-feedback → upstream issue → SKILL-IMPROVE 改造路径。
- **`cataforge feedback ensure-labels`** —— 一次性在上游仓库创建 `framework.json#feedback.gh.labels` 声明的所有 label（幂等，跳过已存在的）。
- **COMMON-RULES §禁止设计阶段与变更说明残留** —— 长期文档 / 源码默认不写版本里程碑、阶段标签、对比叙事；变更说明只属于 CHANGELOG / commit / PR 描述。

### Changed

- **`cataforge feedback --gh` label 来自配置** —— `framework.json#feedback.gh.labels` 三键 `bug` / `suggest` / `correction-export` 各自映射到一组 label；不再在 CLI 代码里硬编码 `feedback,bug` 等上游不存在的 label。`fallback_on_missing_label: true`（默认）让 `gh issue create` 在 label 不存在时自动重试不带 `--label`，并 stderr WARN 提示用户跑 `cataforge feedback ensure-labels`。
- **reflector 默认 inline 执行** —— Retrospective Protocol 由 orchestrator 在主对话直接执行，与 change-guard / Adaptive Review 一致；reflector AGENT.md frontmatter 增 `inline_dispatch: true` hint，`model_tier` 由 light 改为 inherit。手动入口 `cataforge agent run reflector` 仍保留作 fallback。
- **reflector Retrospective Protocol 扫描 `docs/EVENT-LOG.jsonl`** —— `correction` / `incident` / `revision_start` 事件作为补充 evidence 与 review 报告交叉验证；EVENT-LOG 单独不能撑起一条 EXP（仍需 review/CORRECTIONS-LOG 各一条）。
- **PROJECT-STATE.md `Learnings Registry` 字段** —— 模板默认值改为 bounded（容量来自 `framework.json#claude_md_limits.learnings_registry_max_entries`），首次 retrospective 后由 orchestrator append。

### Fixed

- **`cataforge feedback bug --gh` 在干净 fork 上 422 失败** —— 上游若没创建 `feedback` / `triage` / `upstream-gap` 等自定义 label，老版本的硬编码 `--label feedback,bug` 会让 `gh issue create` 直接 422；新版默认与上游 `bug` / `enhancement` 对齐 + 自动 fallback 不再 fail。
