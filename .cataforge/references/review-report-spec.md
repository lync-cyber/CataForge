# 审查报告撰写规约 — review report spec

> 报告产出方（reviewer / qa-engineer 及 doc-review / code-review / sprint-review /
> framework-review / penpot-bridge / walkthrough 系 skill）在写报告时按需加载本文档。
> verdict 语义（归因分类 / 三态判定逻辑 / verdict_blocking_semantics）是跨 Agent 契约，
> 留在 COMMON-RULES §审查报告规范，不在本文件。

## 报告编号规则
- 首次：`REVIEW-{doc_id}-r1.md` 或 `CODE-REVIEW-{task_id}-r1.md`。
- 第 N 次：`-r{N}`，N = 同前缀 `-r*` 文件数 + 1。
- 最新版本 = 编号最大的文件，无需归档重命名。

## 报告 Front Matter 约定
所有系统生成的报告（含审查报告与运维日志）必须以 YAML front matter 起始；缺失会被 `cataforge context index` 跳过、被
`cataforge doctor` 计为 orphan 并 FAIL。

| 报告类别 | 路径 | `id` 格式 | `doc_type` | 允许 `status` |
|---------|------|----------|-----------|--------------|
| 文档审查报告 | `docs/reviews/doc/REVIEW-{doc_id}-r{N}.md` | `review-{doc_id}-r{N}` | `review` | `draft` / `approved` |
| 代码审查报告 | `docs/reviews/code/CODE-REVIEW-{task_id}-r{N}.md` | `code-review-{task_id}-r{N}` | `code-review` | `draft` / `approved` |
| Sprint 审查报告 | `docs/reviews/sprint/SPRINT-REVIEW-*.md` | 见 [`utility/sprint-review.md`](../skills/context/templates/utility/sprint-review.md) | `sprint-review` | `draft` / `approved` |
| 框架元资产审查 | `docs/reviews/framework/FRAMEWORK-REVIEW-{scope}-{YYYYMMDD}-r{N}.md` | `framework-review-{scope}-{YYYYMMDD}-r{N}` | `framework-review` | `draft` / `approved` |
| 设计一致性审查报告 | `docs/reviews/design/DESIGN-REVIEW-{component_id}-r{N}.md` | `design-review-{component_id}-r{N}` | `design-review` | `draft` / `approved` |
| 项目级代码扫描 | `docs/reviews/code/CODE-SCAN-{YYYYMMDD}-r{N}.md` | `code-scan-{YYYYMMDD}-r{N}` | `code-review` | `draft` / `approved` |
| 功能走查报告 | `docs/reviews/walkthrough/WALKTHROUGH-{scope}-{YYYYMMDD}-r{N}.md` | `walkthrough-{scope}-{YYYYMMDD}-r{N}` | `walkthrough` | `draft` / `approved` |
| 上游 issue triage 草稿 | `docs/reviews/triage/SKILL-IMPROVE-{target_id}-issue-{N}.md` | `skill-improve-{target_id}-issue-{N}` | `skill-improve` | `draft` / `approved` |
| 运维订正日志 | `docs/reviews/CORRECTIONS-LOG.md` | `corrections-log` | `correction-log` | `approved` |

最小字段集（doc-review checker 强制 id / author / status / deps / consumers；`consumers` 仅 doc_type ∈
{research, changelog} 豁免）：

```yaml
---
id: "review-{doc_id}-r{N}"        # 或 code-review-{task_id}-r{N} / corrections-log
doc_type: review                  # 或 code-review / sprint-review / correction-log
author: reviewer                  # 审查报告：reviewer；CORRECTIONS-LOG：cataforge
status: draft                     # 出 verdict 后改 approved；CORRECTIONS-LOG 恒为 approved
deps: ["{被审 doc_id 或 task_id}"] # CORRECTIONS-LOG 用 []
consumers: ["{下游消费 agent/skill}"] # doc_type ∈ {research, changelog} 可省
---
```

`status` 取值仅 `draft` / `review` / `approved`（见 doc-review checker），不可写 `closed`。

## 问题格式
```
### [R-{NNN}] {SEVERITY}: {标题}
- **category**: {见 COMMON-RULES §统一问题分类体系}
- **root_cause**: {见 COMMON-RULES §归因分类}
- **members**: [R-xxx, R-yyy] {仅系统性聚类 finding，列被合并升级的成员编号}
- **描述**: {问题描述}
- **建议**: {改进建议}
```
