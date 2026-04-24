# CataForge — Claude Code 项目指令

## Git 工作流

`main` 受保护；所有变更走 feature branch + PR。仓库只允许 Squash merge，PR 标题即 main 的 commit 消息。

**PR 标题：conventional-commits**

```
<type>(<scope>): <subject>
```

- `type` ∈ `feat|fix|docs|chore|refactor|test|build|ci|perf|release`，小写
- `subject` 小写开头、祈使句
- `scope` 示例：`cli`、`scaffold`、`upgrade`、`hook`、`agent`、`skill`、`docs`、`ci`、`e2e`

反例（CI 拒绝）：`Dev`、`Pr/dev …`、`Feat/correction log …`、`Fix/orchestrator …`
正例：`fix(doc-review): ui-spec empty-token FAIL`、`feat(scaffold): manifest + per-file dry-run`、`release: v0.1.8 self-update skill`

校验：`.github/workflows/pr-title.yml`。

**发版流程**
1. feature branch 上完成变更并 commit
2. `git push -u origin <branch>`
3. `gh pr create --title '<type>(<scope>): <subject>'`（必须显式 `--title`，否则 gh 用分支名）
4. 合入后在 main 打 tag：`git tag vX.Y.Z && git push origin vX.Y.Z`

**dogfood 分支 → main**：在 feature 分支跑 `.cataforge/scripts/dogfood/prepare-pr.sh`（按 `product-paths.txt` 白名单还原 dev-only 产物，交互式提示合规标题并调 `gh pr create`）。

**本地误提 main 的补救**：

```bash
git branch <new-branch>
git reset --hard origin/main
git push -u origin <new-branch>
```
