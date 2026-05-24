### Changed

- **tdd-engine/SKILL.md 流程轻量化** —— per-task code-review 改为分级触发：仅 `security_sensitive` / `user_facing_critical_path` / `consumer_components` 非空的高风险任务走即时审查，其余延迟到 sprint-review 批量覆盖；agile-standard 模式的 light 任务放宽为可走 light-inline（审计粒度通过 EVENT-LOG 保持）。
- **ORCHESTRATOR-PROTOCOLS.md Revision Protocol 增量审查** —— revision re-review 仅审查 `git diff` 变更部分，上轮无 CRITICAL/HIGH 的维度标注 `[previously-approved]` 不重复审查；needs_revision 循环上限从 N≥3 收紧到 N≥2。
- **ORCHESTRATOR-PROTOCOLS.md Sprint Review Protocol** —— 新增 Batch Code-Review 机制，对未经 per-task code-review 的延迟任务在 sprint-review 报告中逐任务覆盖 L2 维度。
- **doc-gen 模板 tdd_acceptance 格式** —— standard/lite/sprint-volume/brief 四套模板的 AC 占位符从 `{测试描述} → 预期: {结果}` 改为 Given-When-Then 格式。
- **sprint_review `code_review_present` 严重等级** —— 从 FAIL 降为 WARN，适配延迟批量审查模式。

### Added

- **test-writer/AGENT.md §Behavioral Assertion Mandate** —— 禁止存在性断言（hasattr/isDefined/isNotNone/callable/len>0）6 种模式表 + 假实现检测 + 期望值溯源到 AC Then 子句；测试质量自检从三维度扩展为四维度（+行为验证充分性）。
- **tdd-engine/SKILL.md dispatch prompt 注入 PRD 上下文** —— Step 1 新增 user_story + business_rules 加载；RED/Light Dispatch/Light Inline 三处 prompt 均注入 `## user_story` 段。
- **task-decomp/SKILL.md AC Given-When-Then 格式约束** —— 每条 AC 必须包含 Given（前置条件）、When（触发动作）、Then（可观测结果），禁止"实现 X"等无行为描述的模糊 AC。
- **code-review/SKILL.md §增量审查模式** —— `task_type=revision` 时审查范围收窄到 `git diff` 涉及的文件和函数。
- **typed_checks.py GWT 格式检测** —— doc-review Layer 1 新增 Given/When/Then 关键词检测，AC 缺 GWT 结构发出 WARN。
- **`scripts/checks/check_doc_structure.py`** —— pre-commit + CI 守卫，扫描 `.cataforge/` 下 markdown 文件的非标准步骤编号（3a./4b.）、编号跳跃、编号重复。
- **CLAUDE.md §硬约束 3 · 文档结构规范** —— 编号列表必须使用连续整数，禁止非标准子步骤编号/编号跳跃/编号重复。

### Fixed

- **ORCHESTRATOR-PROTOCOLS.md 非标准步骤编号** —— Bootstrap `3a.` 重编号为连续整数（步骤 3~10）；Revision Protocol `4a.` 合并到步骤 4 行内；Sprint Review `2a.` 合并到步骤 2 行内；Change Request Protocol 重复 `4.` 收拢为散文段落。
