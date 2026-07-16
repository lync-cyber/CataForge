# context · review(单文档门禁)

Layer 1 脚本自动检查 + Layer 2 AI 语义审查双审。审查范围限 `docs/` 业务文档;代码审查由 code-review 负责,框架元资产由 framework-review 负责。

## Layer 1 — 脚本自动检查
单一入口,经框架派发(不直接调内部脚本):
```bash
cataforge skill run doc-review -- {doc_type} docs/{doc_type}/{doc_file} --docs-dir docs/{doc_type}/
```
一个 doc_type 一个逻辑文档(整篇审查),Layer 1 通过才进入 Layer 2。xref / 双向覆盖等检查由框架按当前可用的最高保真后端执行。

**Layer 2 短路**: Layer 1 exit 0、行数 < `DOC_REVIEW_L2_SKIP_THRESHOLD_LINES`、且（`doc_type ∈ DOC_REVIEW_L2_SKIP_DOC_TYPES` 或 frontmatter `mode ∈ {agile-lite, agile-prototype}`）→ 跳过 Layer 2 判 `approved`(仍出报告并标注短路)。lite 文档 doc_type 是基名 prd/arch/dev-plan，靠 `mode` 而非 doc_type 命中短路。非首轮审查命中短路时仍执行 §报告 的 still-open 标注，上轮 notes 不得静默蒸发。

## Layer 2 — AI 语义审查
经 navigate 按需加载被审文档与上游依赖。**双层分工契约**: 形式面(结构/格式/字段/编号/引用可解析)由 Layer 1 独占,Layer 2 不复报可机检问题(除非形式问题引发语义后果);审查报告主体必须来自实质维度,严重度按「缺陷对下游阶段的影响」定级,不按形式醒目程度定级。

通用维度: 完整性 / 一致性 / 可行性 / 安全性 / 清晰度。被审 doc_type 命中下表时**只加载对应单份 profile**,以其实质维度与严重度锚点为主、通用维度兜底:

| doc_type | 实质审查 profile |
|----------|------------------|
| prd | [review-prd.md](review-prd.md) |
| arch | [review-arch.md](review-arch.md) |
| ui-spec | [review-ui-spec.md](review-ui-spec.md) |

未命中 doc_type 沿用通用维度;dev-plan 追加 AC 可观测性,deploy-spec 追加本地最小栈验证证据真实性（§5 须为真实 bring-up 日志而非占位）。可传 `--focus <category[,...]>` 收敛维度。

## 报告
产出 `docs/reviews/doc/REVIEW-{doc_id}-r{N}.md`,首行 YAML front matter(id/doc_type=review/author/status/deps),问题列表含严重等级 CRITICAL/HIGH/MEDIUM/LOW;结论 approved / approved_with_notes / needs_revision。Layer 1 权威检查清单见 doc-review 的 `CHECKS_MANIFEST`。

非首轮审查(同 doc_id 已存在 `-r{N-1}` 报告)时:加载上轮未闭环的 MEDIUM/LOW 清单为已知问题输入,逐条标注 `still-open` / `resolved`;still-open 项参与本轮聚类升级计数,并按本轮 finding 参与三态判定(COMMON-RULES §三态判定逻辑)。

## 修订
needs_revision / inline-fix 的修复经 context authoring(`write-narrative` 写节叙事 / `write` 写实体)落图后 `context finalize` 重导出,不 `Edit` `docs/` 导出文件——图后端就绪时 `docs/` 是图的只读导出视图,直接 Edit 会被 `context reconcile` 判为 human_edit 漂移。
