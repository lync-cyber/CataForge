### Changed

- **`domain/docs/indexer.py` 抽出构建层到 `_index_build.py`** —— 把索引*构建*原语（`build_document_entry` / `build_xref` / `build_full_index` / `build_aliases` / `update_single_doc` / `write_index` / `_make_index` 及 dep-hash / section-meta 等 helper）移入叶子模块 `domain/docs/_index_build.py`；`indexer.py` 保留*校验*面（orphan / stale / xref / alias / invalid-id 检查）与 CLI 入口，并重导出构建器以保持导入面不变。校验器依赖构建器、构建器从不反向依赖，故拆分无环。纯结构性改动，行为等价。
