#!/usr/bin/env bash
# deploy-dev.sh — 在 dev worktree 运行 cataforge deploy 并保留 dogfood CLAUDE.md
#
# 背景:
#   `cataforge deploy` 会用 PROJECT-STATE.md 模板覆盖根 CLAUDE.md。
#   dogfood worktree 的 CLAUDE.md 是手工定制版（agile-lite、dev 规则等），
#   直接 deploy 会丢失。本脚本保留定制版。
#
# 工作流:
#   1. 若 CLAUDE.md 存在，先同步到 .dogfood/CLAUDE.md（作为最新基线）
#   2. 运行 cataforge deploy --platform claude-code
#   3. 将 .dogfood/CLAUDE.md 复制回 CLAUDE.md
#
# 前置:
#   - 在 dev worktree 内运行
#   - .dogfood/CLAUDE.md 已存在（首次运行前需手工创建）
#   - uv 已安装，cataforge package 已可用（uv run cataforge）
#
# 用法:
#   .cataforge/scripts/dogfood/deploy-dev.sh [--check]
#     --check  → 传给 cataforge deploy，只显示将执行的操作

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
    echo "ERROR: 不在 git 仓库中" >&2
    exit 1
fi
cd "$REPO_ROOT"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" == "main" ]]; then
    echo "ERROR: 不要在 main 上运行 deploy-dev.sh，它会生成 dogfood 定制内容" >&2
    echo "       main 应使用 'uv run cataforge deploy --platform claude-code'" >&2
    exit 1
fi

DOGFOOD_DIR=".dogfood"
DOGFOOD_CLAUDE="$DOGFOOD_DIR/CLAUDE.md"
ROOT_CLAUDE="CLAUDE.md"

# 1. 同步最新 CLAUDE.md 到 .dogfood/（如果用户手工改过）
if [[ -f "$ROOT_CLAUDE" ]]; then
    mkdir -p "$DOGFOOD_DIR"
    if [[ ! -f "$DOGFOOD_CLAUDE" ]]; then
        echo ">> 首次运行，将当前 CLAUDE.md 保存为 dogfood 基线"
        cp "$ROOT_CLAUDE" "$DOGFOOD_CLAUDE"
    elif ! cmp -s "$ROOT_CLAUDE" "$DOGFOOD_CLAUDE"; then
        echo ">> 检测到 CLAUDE.md 有本地修改，更新到 $DOGFOOD_CLAUDE"
        cp "$ROOT_CLAUDE" "$DOGFOOD_CLAUDE"
    fi
else
    if [[ ! -f "$DOGFOOD_CLAUDE" ]]; then
        echo "ERROR: 既没有 $ROOT_CLAUDE 也没有 $DOGFOOD_CLAUDE" >&2
        echo "       首次 dogfood 设置请先手工创建 $DOGFOOD_CLAUDE" >&2
        exit 1
    fi
fi

# 2. 运行 cataforge deploy
echo ">> 运行 cataforge deploy --platform claude-code $*"
uv run cataforge deploy --platform claude-code "$@"

# --check 模式不真的写文件，不需要恢复
for arg in "$@"; do
    if [[ "$arg" == "--check" ]]; then
        echo ">> --check 模式，跳过 CLAUDE.md 恢复"
        exit 0
    fi
done

# 3. 恢复 dogfood CLAUDE.md
if [[ -f "$DOGFOOD_CLAUDE" ]]; then
    cp "$DOGFOOD_CLAUDE" "$ROOT_CLAUDE"
    echo ">> CLAUDE.md 已从 $DOGFOOD_CLAUDE 恢复"
else
    echo "WARN: $DOGFOOD_CLAUDE 不存在，CLAUDE.md 保持 deploy 生成的版本" >&2
fi

echo ""
echo "OK — dev worktree 部署完成"
