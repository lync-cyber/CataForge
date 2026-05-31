### Added

- **ingest 写入文档/章节结构节点** —— `cataforge kg import` 在写实体/关系之外,新增 Phase 3b:每个业务文档落一个 `Document` 节点,每个**实体所属章节**落一个 `Section` 节点(携带 `narrative_body` 散文、`content_hash`、`contains_entity` → 其下实体、`part_of_document`),`Document` 经 `has_section` 串联。结构节点以 `id` IRI(`/doc/...`、`/doc/.../sec/...`)标识、不带 `cf:entity_id`,与实体 IRI 隔离;按 `content_hash` 幂等(未变源零新增三元组)。`MigrationStats` 增 `documents_*` / `sections_*` 计数。

### Changed

- **reconcile 纳入结构节点漂移** —— `cataforge kg reconcile` 在实体/关系对称差之外,新增按 `cf:source_doc` 归属的 `Section` 节点对称差(`missing_sections` / `ghost_sections`),计入 `divergence_count`。
- **验证/校验放行结构节点** —— hand-rolled `validate` 的 `entity_id-required` 形状、`verify_after_write` 的实体计数、export 实体枚举均把 Document/Volume/Section 视为 `id` 标识的结构节点排除,不再误报或误算。doctor `kg_ingestion_completeness` 仍为实体级门(结构漂移由 reconcile 守)。
