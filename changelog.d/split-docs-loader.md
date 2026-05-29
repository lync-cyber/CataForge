### Changed

- **`domain/docs/loader.py` 抽出 KG 桥接层到 `_loader_kg.py`** —— 把 `_try_kg_extract` / `_try_kg_plan_load` / `_try_kg_resolve_deps` / `_entity_id_to_ref` / `_all_active_parsed_refs`（KG-active 时的图分流，含惰性 kg 导入）移入 `domain/docs/_loader_kg.py`；公共 `extract` / `plan_load` / `resolve_deps` 仍在 `loader.py`。`parse_ref` 下沉到叶子模块 `index_ops.py`（与既有 ref 异常 / doc_type 映射同处），由 `loader` 重导出以保持 `loader.parse_ref` 与 `indexer` 的导入面，避免 loader↔_loader_kg 循环。纯结构性改动，行为等价。
