### Added

- **sprint-review 三档模式 + `project_features` schema** —— sprint-review SKILL.md §审查档位 正式声明 standard / lite / **merged-review** 三档（merged-review 之前隐式存在，5 次实战稳定但框架文档未承认）。dev-plan 主卷 frontmatter 新增可选 `project_features` 块（`merged_review` / `deliverables_accept_alternation` / `unplanned_glob_patterns` 三键），由 `cataforge.skill.builtins.sprint_review.sprint_check.load_project_features()` 加载。

### Changed

- **`sprint_check.py` Layer 1 三处升级** —— (A) `check_code_reviews` 在 `merged_review: true` 时短路 per-task CODE-REVIEW 检查（消除 9+8+1=18 次跨 sprint 误报）；(B) `check_deliverables` 支持 `accept_alternation` 模式，把 `A | B` 行视为或关系（任一存在即过），同时 `check_unplanned_files` 把两候选都标为 planned；(C) `check_unplanned_files` 新增 `glob_whitelist` 参数（来自 `unplanned_glob_patterns`），fnmatch 模式列表过滤 gold-plating WARN（典型用途：`**/*.test.ts` / `**/helpers/*` 等项目级命名约定）。所有键默认关闭，旧项目零迁移；新增 15 个 unit test 覆盖三处行为 + frontmatter 加载 + 主卷/分卷边界。闭环 [#106](https://github.com/lync-cyber/users/CataForge/issues/106) EXP-003 + EXP-005 + EXP-008。
