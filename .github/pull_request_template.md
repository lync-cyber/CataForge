## Summary

<!-- 一到三句话说明本 PR 的目的与范围 -->

-
-

## 来源分支

- [ ] 从 `dev` 分支经 `prepare-pr.sh` 生成（形态 C dogfood 工作流）
- [ ] 基于 main 的常规 feature/fix 分支
- [ ] 其他（请说明）

## Dogfood 自检

如果 PR 来自 dev 分支，必须全部勾选:

- [ ] 已运行 `.cataforge/scripts/dogfood/prepare-pr.sh` 生成本分支
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
