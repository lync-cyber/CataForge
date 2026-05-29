### Removed

- **`cataforge.domain.kg._shim` 向后兼容层** —— 删除 0.4.x 业务文档调用点的 8 个 shim wrapper（`extract` / `extract_batch` / `extract_with_body` / `plan_load` / `build_full_index` / `resolve_deps` / `legacy_validate_report` / `source_section`）。该模块自始仅被测试引用，无任何生产调用点；调用方应直接使用 typed `KnowledgeGraph` API。同时移除已失效的 `check_deprecation_quota.py` 守卫（其正则匹配的模块路径 `cataforge.kg._shim` 与实际路径 `cataforge.domain.kg._shim` 不符，长期为 no-op）。
