#!/usr/bin/env bash
# prepare-pr.sh — 从 dogfood 分支生成可 PR 到 main 的干净分支
#
# 工作流（形态 C）:
#   1. 在 dev 分支（或其他 dogfood 工作分支）跑 orchestrator、改代码
#   2. 要 PR 时运行本脚本: .cataforge/scripts/dogfood/prepare-pr.sh
#   3. 脚本创建 pr/<源分支>-<时间戳> 分支
#   4. 对比 origin/main，将不在 product-paths.txt 白名单内的改动还原
#   5. 提交一条 "chore: reset dogfood artifacts" commit
#   6. 提示你 push + 开 PR
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
    echo ""
    echo "OK — PR 分支已准备: $PR_BRANCH"
    echo ""
    echo "下一步:"
    echo "  git push -u origin $PR_BRANCH"
    echo "  gh pr create --base main --head $PR_BRANCH"
    exit 0
fi

for f in "${RESET_FILES[@]}"; do
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
if ! git diff --cached --quiet; then
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
echo "下一步:"
echo "  git push -u origin $PR_BRANCH"
echo "  gh pr create --base main --head $PR_BRANCH"
echo ""
echo "完成后可删除 PR 分支:"
echo "  git checkout $SRC_BRANCH && git branch -D $PR_BRANCH"
