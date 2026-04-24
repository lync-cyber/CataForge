# CataForge — Claude Code 项目指令

## Git 工作流

`main` 为**受保护分支**，禁止直接 push。所有变更必须通过 feature branch + PR 合入。

（`dev` 分支已于 2026-04-24 废弃。历史上 dogfood 工作流以 `dev` 为长期开发分支、经 `prepare-pr.sh` 生成 PR 分支；现在改为：任意 feature 分支直接调用 `prepare-pr.sh` 过滤掉 dogfood 产物即可。）

**仓库 merge 策略**：只开启 Squash merge，并在 GitHub Settings → General → Pull Requests 勾选 "Default to PR title for squash merge commits"。这样 main 的线性历史 = PR 标题列表，PR 标题必须语义化。

**PR 标题规范（conventional-commits）**：

```
<type>(<scope>): <subject>
```

- `type` ∈ `feat|fix|docs|chore|refactor|test|build|ci|perf|release`，小写
- `subject` 以小写开头，祈使句
- 反例（**会被 CI 拒绝**）：`Dev`、`Pr/dev 20260424 105745`、`Feat/correction log resilience 20260424`
- 正例：`fix(doc-review): ui-spec empty-token FAIL`、`release: v0.1.8 self-update skill`

CI 通过 `.github/workflows/pr-title.yml` 强制校验。

**发版流程**：
1. 在功能/修复分支上完成变更并 commit
2. `git push -u origin <branch>` 推送分支
3. `gh pr create --title '<type>(<scope>): <subject>'` 开 PR（**必须显式传 `--title`**，否则 gh 默认用分支名），等待 CI 通过后合入
4. 合入后在 `main` 上打 tag：`git tag vX.Y.Z && git push origin vX.Y.Z`

**dogfood（orchestrator / 生成物污染）分支 → main 的 PR**：在 feature 分支上跑 `.cataforge/scripts/dogfood/prepare-pr.sh`。脚本会依 `product-paths.txt` 白名单还原 dev-only 产物，然后在交互式环境提示你输入符合 conventional-commits 的标题并自动调用 `gh pr create`，不要手动跳过提示。

**常见错误**：不要在本地 `main` 上 commit 后直接 `git push`——受保护分支会拒绝。
若已提交到本地 `main`，用以下方式补救：

```bash
git branch <new-branch>        # 在当前 commit 创建新分支
git reset --hard origin/main   # 将 main 还原到远端状态
git push -u origin <new-branch>
```
