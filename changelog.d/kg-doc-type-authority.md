### Added

- **实体定义 doc_type 权威表** —— 实体类的定义仅在其权威 doc_type 中成立（Feature/AC→prd、Task→dev-plan、TestCase→test-report 等，单一事实源为 `ENTITY_CLASS_TO_DOC_TYPE`）；非权威 doc_type 中的 heading-subject 与 subordinate 命中降级为引用，不产出定义——test-report 按任务分节复述 T-xxx 不再触发 collision 中止导入。subordinate（AC）的权威跟随其 parent 实体类。项目可经 `framework.json#context.kg_definition_authority`（`{class_name: [doc_type, ...]}`）合并扩展缺省权威（只增不减）。

### Changed

- **collision 迁移引导** —— `KGEntityCollisionError` 消息与 doctor `kg_ingestion_completeness` FAIL 输出逐条列出 `source_doc :: source_section`，并给出动作建议：统一到权威定义，其余出现改 xref（`doc_id#§N.ENTITY-ID`）或行内 code。
- **dangling WARN 降噪** —— doctor 悬挂引用按前缀聚合：全库无任何定义的前缀输出单行汇总（`N TC- id(s) referenced, none defined in active sources (e.g. …)`），有定义的前缀仍逐 id 列出（上限 5 + 省略号）。
