### Fixed

- **KG entity authority override now resolves consistently across the read/repair surface** —— `reconcile` / `repair` / `compare-read` / `context write-doc` 此前忽略 `context.kg_definition_authority`，只在 `import` 链路生效，导致项目把某类实体（如 `Component`）定义到非默认 doc_type 时被 `reconcile` 全数判为 ghost、`repair` 无法重导、`compare-read` 静默漏审、`write-doc` 不写实体。四处现统一经 `definition_authority(project_root)` 解析并下传 `extract_entities`，authority 解析有单一事实来源。
- **`pip` / `uv` 解析不再尝试构建废弃的 `pytest-logging`** —— `linkml-runtime → prefixcommons` 误把测试工具 `pytest-logging`（仅存 2015 sdist，在现代 setuptools 上构建失败）列为运行时依赖。新增 `[tool.uv] override-dependencies` 用永假 marker 将其从解析树剔除。
