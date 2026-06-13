# context · review(单文档门禁)

Layer 1 脚本自动检查 + Layer 2 AI 语义审查双审。审查范围限 `docs/` 业务文档;代码审查由 code-review 负责,框架元资产由 framework-review 负责。

## Layer 1 — 脚本自动检查
单一入口,经框架派发(不直接调内部脚本):
```bash
cataforge skill run doc-review -- {doc_type} docs/{doc_type}/{doc_file} --docs-dir docs/{doc_type}/
```
分卷加 `--volume-type {type}`。所有分卷必须全部通过 Layer 1 才进入 Layer 2。xref / 双向覆盖等检查由框架按当前可用的最高保真后端执行,Agent 无需感知后端。

**Layer 2 短路**: Layer 1 exit 0、行数 < `DOC_REVIEW_L2_SKIP_THRESHOLD_LINES`、且（`doc_type ∈ DOC_REVIEW_L2_SKIP_DOC_TYPES` 或 frontmatter `mode ∈ {agile-lite, agile-prototype}`）→ 跳过 Layer 2 判 `approved`(仍出报告并标注短路)。lite 文档 doc_type 是基名 prd/arch/dev-plan，靠 `mode` 而非 doc_type 命中短路。

## Layer 2 — AI 语义审查
经 navigate 按需加载被审文档与上游依赖,按维度审查: 完整性 / 一致性 / 可行性 / 安全性 / 规范性 / 清晰度;dev-plan 追加 AC 可观测性,ui-spec 追加设计方向/色彩/组件可区分性/空间构成/无障碍,deploy-spec 追加本地最小栈验证证据真实性（§5 须为真实 bring-up 日志而非占位）。可传 `--focus <category[,...]>` 收敛维度。

## 报告
产出 `docs/reviews/doc/REVIEW-{doc_id}-r{N}.md`,首行 YAML front matter(id/doc_type=review/author/status/deps),问题列表含严重等级 CRITICAL/HIGH/MEDIUM/LOW;结论 approved / approved_with_notes / needs_revision。Layer 1 权威检查清单见 doc-review 的 `CHECKS_MANIFEST`。

## 修订
needs_revision / inline-fix 的修复经 context authoring(`write-narrative` 写节叙事 / `write` 写实体)落图后 `context finalize` 重导出,不 `Edit` `docs/` 导出文件——图后端就绪时 `docs/` 是图的只读导出视图,直接 Edit 会被 `context reconcile` 判为 human_edit 漂移。
