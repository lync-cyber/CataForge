### Added

- **`context.strategy` 配置契约** —— framework.json 新增 `context` 段,`strategy ∈ {kg-first, doc-only}`(默认 `kg-first`),声明上下文 I/O 的后端拓扑:`kg-first` 以知识图谱为事实源、Markdown 为导出审查视图;`doc-only` 以 Markdown 为源、无图后端。`cataforge.domain.kg._dispatch.context_strategy(project_root)` 解析(缓存,未声明 / 非法值回退默认)。

### Changed

- **`kg_active_doc_types` 迁移到 `context` 段** —— 该键从 `kg` 段移到 `context.kg_active_doc_types`,成为上下文 I/O 路由是否走图的规范归属;`kg` 段只保留 store 级连接配置(store_backend / db_path / 命名空间)。`_dispatch.active_doc_types`、doctor `kg_ingestion`、scaffold upgrade 保留逻辑、`kg import` 默认范围、`workflow-framework-generator` 模板均改读 `context`。
