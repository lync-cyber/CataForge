### Added

- **Approved-with-Notes Protocol 选项 (4) 全量 inline-fix** —— ORCHESTRATOR-PROTOCOLS §Approved-with-Notes 新增第 4 个用户决策路径：MEDIUM/LOW 问题数 ≥ 8 且全部为表述漂移 / 格式 / 引用对齐 / 完整性补充（非设计缺陷）时，orchestrator/reviewer 主线程逐条 inline-fix（同会话），完成后 verdict 保持 approved_with_notes 但实质等价 approved，文档 status: draft → approved；REVIEW 报告末尾追加 §Inline-Fix 闭环记录 表。不适用 PRD / ARCH 等需求冻结类文档（防止文档冻结后被静默改动）。闭环 [#106](https://github.com/lync-cyber/CataForge/issues/106) EXP-009。
