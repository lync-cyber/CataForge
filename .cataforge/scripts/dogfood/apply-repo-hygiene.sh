#!/usr/bin/env bash
# apply-repo-hygiene.sh — 一次性仓库卫生修复
#
# 做两件事（都需要 `gh auth login` 且有仓库 admin 权限）:
#   1. 重命名历史上的垃圾 PR 标题（#50、#53、#54），让 GitHub PR 列表可读
#      注意: 已 merge 的 PR 改标题**不会**改 main 上的 commit message，
#      那些 commit 已永久固化。此步只修 PR 页面，不 rewrite git 历史。
#   2. 配置仓库 merge 策略: 只允许 squash，默认用 PR title
#
# 用法:
#   gh auth login           # 若未登录
#   .cataforge/scripts/dogfood/apply-repo-hygiene.sh [--dry-run]

set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi

REPO="lync-cyber/CataForge"

run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "DRY-RUN $ $*"
    else
        echo "RUN $ $*"
        "$@"
    fi
}

if ! gh auth status >/dev/null 2>&1; then
    echo "ERROR: gh 未登录。先运行 'gh auth login'。" >&2
    exit 1
fi

# ---- 1. 重命名历史 PR 标题 ----
# 对照 git log 写死；如有新发现再追加。
declare -a RENAMES=(
    "50|chore(dogfood): sync dev into main (2026-04-24)"
    "53|chore(dogfood): sync dev into main (post v0.1.8)"
    "54|feat(correction-log): resilience on partial writes"
)

for entry in "${RENAMES[@]}"; do
    pr="${entry%%|*}"
    new_title="${entry#*|}"
    echo ""
    echo "=== PR #$pr → $new_title"
    run gh pr edit "$pr" --repo "$REPO" --title "$new_title"
done

# ---- 2. 仓库 merge 策略 ----
# delete_branch_on_merge + squash-only 由 `cataforge git ensure-policy` 幂等设置
# （读 framework.json#git.remote_policy，仅在漂移时 PATCH）。
echo ""
echo "=== 仓库 merge 策略: delete-branch-on-merge + squash-only ==="
if [[ $DRY_RUN -eq 1 ]]; then
    run cataforge git ensure-policy --dry-run
else
    run cataforge git ensure-policy
fi

echo ""
echo "OK — 仓库卫生修复完成。"
echo "注: main 线性历史上已存在的 'Dev (#53)'、'Pr/dev 20260424 105745 (#50)'"
echo "    等 commit message 无法安全修改（会 rewrite 受保护分支历史），只能接受。"
echo "    从下一个 PR 起，CI + 仓库设置会确保不再出现此类标题。"
