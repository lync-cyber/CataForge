#!/usr/bin/env bash
# prepare-pr.sh — 从 dogfood 工作分支生成可 PR 到 main 的干净分支
#
# 工作流（形态 C）:
#   1. 在 feature 分支跑 orchestrator、改代码（产物会污染 dev-only 文件）
#   2. 要 PR 时运行本脚本: .cataforge/scripts/dogfood/prepare-pr.sh
#   3. 脚本创建 pr/<源分支>-<时间戳> 分支
#   4. 对比 origin/main，将不在 product-paths.txt 白名单内的改动还原
#   5. 提交一条 "chore: reset dogfood artifacts" commit
#   6. 交互式提示 conventional-commits 标题并自动开 PR
#
# 退出码:
#   0 — 成功（或无需 reset）
#   1 — 参数/环境错误
#   2 — git 操作失败

set -euo pipefail

# -------- 路径 --------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
    echo "ERROR: 不在 git 仓库中" >&2
    exit 1
fi
cd "$REPO_ROOT"

WHITELIST_FILE=".cataforge/scripts/dogfood/product-paths.txt"
BASE="${DOGFOOD_BASE:-origin/main}"

if [[ ! -f "$WHITELIST_FILE" ]]; then
    echo "ERROR: 白名单文件不存在: $WHITELIST_FILE" >&2
    exit 1
fi

# -------- 检查工作区干净 --------
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: 工作区有未提交改动，请先 commit/stash" >&2
    git status --short
    exit 2
fi

# -------- 同步 base --------
echo ">> 拉取 $BASE..."
git fetch origin main --quiet

SRC_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$SRC_BRANCH" == "main" || "$SRC_BRANCH" == "HEAD" ]]; then
    echo "ERROR: 不能在 main 或 detached HEAD 上运行此脚本" >&2
    exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
PR_BRANCH="pr/${SRC_BRANCH}-${TIMESTAMP}"

echo ">> 源分支 : $SRC_BRANCH"
echo ">> 基准   : $BASE"
echo ">> PR分支 : $PR_BRANCH"

git checkout -b "$PR_BRANCH"

# -------- 读白名单 --------
WHITELIST=()
while IFS= read -r raw; do
    # 去除 `#` 注释与前后空白
    line="${raw%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    WHITELIST+=("$line")
done < "$WHITELIST_FILE"

echo ">> 白名单: ${#WHITELIST[@]} 条"

# -------- 列出与 base 的差异 --------
mapfile -t CHANGED < <(git diff --name-only "$BASE"...HEAD)

if [[ ${#CHANGED[@]} -eq 0 ]]; then
    echo ">> 与 $BASE 无差异，无需 reset"
    echo "   PR 分支 $PR_BRANCH 已创建但可能没有内容可 PR"
    exit 0
fi

echo ">> 与 $BASE 的差异文件: ${#CHANGED[@]} 个"

# -------- 白名单过滤 --------
RESET_FILES=()
KEEP_COUNT=0

for f in "${CHANGED[@]}"; do
    keep=0
    for prefix in "${WHITELIST[@]}"; do
        if [[ "$prefix" == */ ]]; then
            # 目录前缀匹配
            if [[ "$f" == "$prefix"* ]]; then
                keep=1
                break
            fi
        else
            # 单文件精确匹配
            if [[ "$f" == "$prefix" ]]; then
                keep=1
                break
            fi
        fi
    done

    if [[ $keep -eq 1 ]]; then
        KEEP_COUNT=$((KEEP_COUNT + 1))
    else
        RESET_FILES+=("$f")
    fi
done

echo ">> 保留: $KEEP_COUNT 个产品文件"
echo ">> 还原: ${#RESET_FILES[@]} 个非白名单文件"

# -------- 执行 reset --------
if [[ ${#RESET_FILES[@]} -eq 0 ]]; then
    echo ">> 无需还原"
    SKIP_RESET_COMMIT=1
else
    SKIP_RESET_COMMIT=0
fi

for f in "${RESET_FILES[@]:-}"; do
    [[ -z "$f" ]] && continue
    echo "   RESET $f"
    if git cat-file -e "$BASE:$f" 2>/dev/null; then
        # 文件在 base 中存在，还原为 base 版本
        git checkout "$BASE" -- "$f"
    else
        # 文件在 base 中不存在（dev 上新建），删除
        git rm -f --quiet "$f" 2>/dev/null || rm -f "$f"
    fi
done

# -------- 提交 reset --------
if [[ "$SKIP_RESET_COMMIT" -eq 0 ]] && ! git diff --cached --quiet; then
    git commit -m "chore: reset dogfood artifacts before PR

白名单来源: $WHITELIST_FILE
还原文件数: ${#RESET_FILES[@]}
源分支    : $SRC_BRANCH
"
    echo ">> 已提交 reset commit"
fi

echo ""
echo "OK — PR 分支已准备: $PR_BRANCH"
echo ""

# -------- 交互式开 PR（防垃圾标题） --------
# 历史教训: 直接 `gh pr create` 会默认用分支名作标题，
# 产生 "Pr/dev 20260424 105745 (#50)" 这种无语义 commit 固化到 main。
# 此段强制用 conventional-commits 标题开 PR。
TITLE_REGEX='^(feat|fix|docs|chore|refactor|test|build|ci|perf|release)(\([a-z0-9._/-]+\))?!?: [a-z].+'

prompt_title() {
    local title=""
    while true; do
        read -r -p "PR 标题 (conventional-commits, 例: fix(scope): lower-case subject): " title
        if [[ "$title" =~ $TITLE_REGEX ]]; then
            printf '%s' "$title"
            return 0
        fi
        echo "  x 不符合 ^type(scope): subject 格式，或 subject 以大写开头。请重试。" >&2
    done
}

if command -v gh >/dev/null 2>&1 && [[ -t 0 ]]; then
    echo "下一步（推荐，自动开 PR）:"
    read -r -p "现在推送并开 PR？[y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        PR_TITLE="$(prompt_title)"
        git push -u origin "$PR_BRANCH"
        gh pr create --base main --head "$PR_BRANCH" --title "$PR_TITLE" --body "$(cat <<EOF
## Source branch
\`$SRC_BRANCH\` → reset via \`prepare-pr.sh\`

## Whitelist
\`$WHITELIST_FILE\` (${#WHITELIST[@]} entries) · reset ${#RESET_FILES[@]} / kept $KEEP_COUNT
EOF
)"
        echo ""
        echo "完成后可删除 PR 分支:"
        echo "  git checkout $SRC_BRANCH && git branch -D $PR_BRANCH"
        exit 0
    fi
fi

echo "下一步（手动）:"
echo "  git push -u origin $PR_BRANCH"
echo "  gh pr create --base main --head $PR_BRANCH --title '<type>(<scope>): <subject>'"
echo ""
echo "  ⚠ 不要省略 --title，否则 gh 会用分支名作标题（小写 type/scope 规范见 CLAUDE.md）"
echo ""
echo "完成后可删除 PR 分支:"
echo "  git checkout $SRC_BRANCH && git branch -D $PR_BRANCH"
