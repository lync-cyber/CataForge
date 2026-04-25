# Dogfood Workflow

CataForge 用自己开发自己。本目录提供"feature 分支跑 orchestrator → prepare-pr.sh
剥离过程产物 → PR 到 main"工作流的工具。

> **2026-04 调整**：原"长期 dev 分支 + PR-to-main"模型已退役（dev 分支不再
> 存在于 origin），改为每个改动独立 feature 分支模型。脚本头注释（[prepare-pr.sh](prepare-pr.sh)）
> 是当前权威说明；本 README 与之对齐。

## 架构

```
main (干净, 仅产品文件)
 ^
 | PR (仅白名单内文件)
 |
 +-- pr/<feature>-<timestamp>   <- prepare-pr.sh 自动生成
            ^
            | reset 非产品文件 (orchestrator 过程产物)
            |
           feat/<topic> 或 fix/<topic>
            |  在该分支上跑 orchestrator、改代码
            |  过程产物（PROJECT-STATE、EVENT-LOG、prd-lite 等）短暂存在于工作树
            |  绝大多数被 .gitignore 拦截，不进 git
```

## 文件

| 文件 | 作用 |
|---|---|
| [product-paths.txt](product-paths.txt) | 产品文件白名单 — 只有这些路径允许 PR 到 main |
| [prepare-pr.sh](prepare-pr.sh) | 从当前 feature 分支生成干净的 `pr/*` 分支并交互式开 PR |

> **历史**: 本目录曾有 `deploy-dev.sh`，用于在每次 `cataforge deploy` 后恢复
> dogfood 定制的 CLAUDE.md。自框架引入 `instruction_file.targets[].update_strategy:
> section-merge` 后，deploy 会直接按章节保留用户定制，包装器不再必要，已下线。
> 详见框架 profile.yaml 的 `section_policy` 字段。

## 日常工作流

### 1. 在 feature 分支工作

```bash
git checkout main && git pull
git checkout -b feat/<topic>            # 或 fix/<issue>-<topic>

# 跑 orchestrator、改代码、写过程 doc
# 过程产物大多被 .gitignore 拦截，少量进入工作树（PROJECT-STATE 等）
# 产品改动建议每个语义提一条 commit，过程产物本身不必单独 commit
git commit -m "feat(skill): add new capability"
```

### 2. 准备 PR

```bash
# 在 feature 分支上运行（工作区必须干净）
.cataforge/scripts/dogfood/prepare-pr.sh
```

脚本会:

1. 创建 `pr/<源feature分支>-<时间戳>` 分支
2. 对比 `origin/main`，找出所有差异文件
3. 把不在 `product-paths.txt` 白名单里的文件还原为 main 的版本
4. 提一条 `chore: reset dogfood artifacts before PR` commit
5. 交互式提示 conventional-commits PR 标题，调 `gh pr create` 自动开 PR

合入采用 squash merge；PR 标题即 main 上的 commit 消息（见 [CLAUDE.md](../../../CLAUDE.md) §Git 工作流）。

### 3. 合入后清理 feature 分支

PR squash merge 后，main 上多了一条 commit。本地清理:

```bash
git checkout main
git pull
git branch -D feat/<topic>              # 删除本地 feature 分支
git branch -D pr/<feature>-<timestamp>  # 删除生成的 PR 分支
```

不需要 "把 main 拉回 dev" 这样的同步步骤 —— 没有长期分支。

## 白名单扩展

新增产品路径时，走正常 feature/fix PR：

```bash
git checkout main && git pull
git checkout -b chore/whitelist-add-X
# 编辑 .cataforge/scripts/dogfood/product-paths.txt
git commit -am "chore(dogfood): whitelist docs/examples/"
git push -u origin chore/whitelist-add-X
gh pr create --base main --title "chore(dogfood): whitelist docs/examples/"
```

## CI 护栏

[`.github/workflows/no-dogfood-leak.yml`](../../../.github/workflows/no-dogfood-leak.yml) 在每个 PR 上运行，拒绝:

- `.dogfood/` 下的任何文件
- `docs/EVENT-LOG.jsonl`、`docs/CORRECTIONS-LOG.md`、`docs/NAV-INDEX.md`
- `docs/prd/`、`docs/arch/`、`docs/dev-plan/` 等过程目录
- `docs/brief.md`、`docs/*-lite.md`
- `.cataforge/PROJECT-STATE.md` 的任何未配套 scaffold 镜像同步的修改

即使忘跑 `prepare-pr.sh`，CI 也会兜底。

## Troubleshooting

**"工作区有未提交改动"** — 先 `git commit` 或 `git stash`。

**"不能在 main 或 detached HEAD 上运行"** — 切到任意 feature/fix 分支。

**PR 里意外出现某个文件** — 该文件不在白名单里，应该在 `product-paths.txt` 里
加上路径（如果是产品），或确认它是否本应被 `.gitignore` 拦截（如果是过程产物）。

**CI 报 PROJECT-STATE 被修改** — `git checkout origin/main -- .cataforge/PROJECT-STATE.md`
还原后再次提交，或如果是模板真改动，需要同时同步 scaffold 镜像（详见
no-dogfood-leak.yml 的提示）。

**CLAUDE.md 被 deploy 覆盖** — 框架的 `update_strategy: section-merge`（见各
platform profile.yaml 的 `section_policy`）会按章节保留用户定制内容。若仍出现
覆盖，检查 profile 是否声明了该策略，且目标章节是否列在 `schema` 或未列出
（走 `user_extensible`）。
