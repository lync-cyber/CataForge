# Dogfood Workflow (形态 C)

CataForge 用自己开发自己。本目录提供"dev 长期分支 + PR-to-main"工作流的工具。

## 架构

```
main (干净)
 ^
 | PR (仅白名单内文件)
 |
 +-- pr/dev-<timestamp>   <- prepare-pr.sh 自动生成
            ^
            | reset 非产品文件
            |
           dev (长期 dogfood 分支)
            |  orchestrator 过程产物都在这里
            |  PROJECT-STATE、EVENT-LOG、prd-lite.md 等
```

## 文件

| 文件 | 作用 |
|---|---|
| [product-paths.txt](product-paths.txt) | 产品文件白名单 — 只有这些路径允许 PR 到 main |
| [prepare-pr.sh](prepare-pr.sh) | 从当前分支生成干净的 PR 分支 |

## 日常工作流

### 1. 在 dev 分支工作

```bash
# 进入 dev worktree（首次: git worktree add ../CataForgeNext-dev dev）
cd ../CataForgeNext-dev

# 随意跑 orchestrator、改代码、写过程 doc
# 过程产物由 .gitignore 拦截，不会进 git
# 产品改动和 dogfood 改动推荐分 commit:
git commit -m "feat(skill): add new capability"
git commit -m "dogfood: bump PROJECT-STATE"

git push origin dev
```

### 2. 准备 PR

```bash
# 在 dev 分支上运行（工作区必须干净）
./.cataforge/scripts/dogfood/prepare-pr.sh

# 输出示例:
#   OK — PR 分支已准备: pr/dev-20260417-150000
#   下一步:
#     git push -u origin pr/dev-20260417-150000
#     gh pr create --base main --head pr/dev-20260417-150000
```

脚本会:
1. 创建 `pr/<源分支>-<时间戳>` 分支
2. 对比 `origin/main`，找出所有差异文件
3. 把不在 `product-paths.txt` 白名单里的文件还原为 main 的版本
4. 提一条 `chore: reset dogfood artifacts` commit

### 3. 合入后同步 dev

PR merge（squash）后，main 上多了一条 commit。把它拉回 dev:

```bash
cd ../CataForgeNext-dev
git checkout dev
git fetch origin main
git merge origin/main   # 保留 dev 的过程产物，带入 main 新改动
```

不要 `git merge dev` 到 main — 形态 C 的纪律是 **dev 永不直接合入**。

## 白名单扩展

新增产品路径时:

```bash
# 在 main 上改 product-paths.txt，走正常 PR
git checkout main
git checkout -b chore/whitelist-add-X
# 编辑 .cataforge/scripts/dogfood/product-paths.txt
git commit -am "chore(dogfood): whitelist docs/examples/"
gh pr create --base main
```

合入后从 dev 同步: `git merge origin/main`。

## CI 护栏

`.github/workflows/no-dogfood-leak.yml` 在每个 PR 上运行，拒绝:
- `.dogfood/` 下的任何文件
- `docs/EVENT-LOG.jsonl`、`docs/CORRECTIONS-LOG.md`、`docs/NAV-INDEX.md`
- `docs/prd/`、`docs/arch/`、`docs/dev-plan/` 等过程目录
- `docs/brief.md`、`docs/*-lite.md`
- `.cataforge/PROJECT-STATE.md` 的任何修改

即使忘跑 `prepare-pr.sh`，CI 也会兜底。

## Troubleshooting

**"工作区有未提交改动"** — 先 `git commit` 或 `git stash`。

**"不能在 main 或 detached HEAD 上运行"** — 切到 dev 或其他工作分支。

**PR 里意外出现某个文件** — 该文件不在白名单里，应该在 `product-paths.txt` 里加上路径（如果是产品），或确认是否应该 ignore（如果是过程产物）。

**CI 报 PROJECT-STATE 被修改** — `git checkout origin/main -- .cataforge/PROJECT-STATE.md` 还原后 amend。
