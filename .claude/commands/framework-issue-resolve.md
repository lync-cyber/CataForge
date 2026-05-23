---
description: Triage / propose / close upstream CataForge GitHub issues. Five-step loop defined in framework-issue-resolve SKILL.
---

按 `.cataforge/skills/framework-issue-resolve/SKILL.md` 的五步闭环处理上游 GitHub issue：

1. **拉取**：`cataforge issue triage --dry-run` 看 verdict 表
2. **分析**：写 SKILL-IMPROVE 草稿到 `docs/reviews/triage/SKILL-IMPROVE-<id>-issue-<N>.md`
3. **判定**：给 verdict + rationale + 修复路径（**maintainer go/no-go**）
4. **实施**：feature 分支 + Edit + commit + PR（标准 dev 流程，见 [CLAUDE.md §Git 工作流](../../CLAUDE.md)）
5. **关闭**：PR merge 后 `cataforge issue close <N> --verdict fixed --pr <P>`

调度时先 Read 上述 SKILL.md 拿完整协议（含 verdict 五态、close comment 模板、Anti-Patterns）。

**硬约束**：步骤 3↔4 是 maintainer 强制 checkpoint。未拿到明确 go-ahead 前不写代码改动；PR 未 merge 前不 close issue。
