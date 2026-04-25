## Summary

<!-- 一到三句话说明本 PR 的目的与范围 -->

-
-

## 来源分支

- [ ] 从 feature 分支经 `.cataforge/scripts/dogfood/prepare-pr.sh` 生成（dogfood 工作流；产物在 feature 分支跑过 orchestrator 后用脚本剥离）
- [ ] 基于 main 的常规 feature/fix 分支（无 orchestrator 产物污染）
- [ ] 其他（请说明）

## Dogfood 自检

如果 PR 来自 dogfood 工作流（已勾选上方第一项），必须全部勾选:

- [ ] 已运行 `.cataforge/scripts/dogfood/prepare-pr.sh` 生成本 PR 分支（脚本头注释为权威说明，参考 dogfood/README.md）
- [ ] `.cataforge/PROJECT-STATE.md` 未被修改
- [ ] 未包含 `docs/EVENT-LOG.jsonl` / `docs/CORRECTIONS-LOG.md` / `docs/NAV-INDEX.md`
- [ ] 未包含 `docs/prd/` / `docs/arch/` / `docs/dev-plan/` / `docs/reviews/` 等过程目录
- [ ] 未包含 `docs/brief.md` / `docs/*-lite.md`
- [ ] 未包含 `.dogfood/` 下的任何文件

> CI `No dogfood leak` 会自动兜底检查，未勾选会被拒绝合入。

## Test plan

- [ ]
- [ ]

## Related

<!-- 关联的 issue / PR / 设计文档 -->
