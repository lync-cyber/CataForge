### Removed

- **删除已被 context 取代的扁平 skill** —— 移除 `doc-nav` / `doc-gen` / `doc-review` / `doc-consistency` / `kg-ask` 五个 `.cataforge/skills/*/SKILL.md`(及目录),其能力已收敛进 `context` 父 skill 的 navigate/generate/review/consistency/query 分支。`doc-gen` 的 `templates/` 迁入 `.cataforge/skills/context/templates/`。`doc-review` / `doc-consistency` 的 runtime builtin 保留,`cataforge skill run doc-review|doc-consistency` 经 `_BUILTIN_ID_MAP`(新增 `doc_consistency` 映射)继续解析,作为 context review/consistency 分支的 Layer-1 引擎。

### Changed

- **全量重指引用与守卫至 context** —— 13 个 AGENT.md 的 `skills:`、17 个 SKILL.md 的 `depends:`、harness 散文、`doctor` migration_checks(模板/常量锚点)、doc_review 模板注册表路径(`template_registry.py`)、framework-review 常量(`ORPHAN_SKILL_WHITELIST` / `B1_REQUIRED_SECTIONS_EXEMPT_SKILLS`)、skill 计数文档(31 → 26)、agents-and-skills 目录与 agent→skill 映射,统一指向 `context`(或其 builtin)。framework-review `all` 由基线 3 WARN 收敛为 0 FAIL / 0 WARN。
