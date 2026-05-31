### Added

- **KG 文档/章节/卷本体** —— `core.yaml` 新增 `Document` / `Volume` / `Section` 三个结构性类(与 `Project` 同为 standalone,以 `id` 标识,不继承 `SoftwareArtifact` 的 entity_id/sort_key 约束)。`Section` 携带 `narrative_body`(散文)与 `contains_entity`(其下结构化实体),`SoftwareArtifact` 增 `located_in_section` 回指;配套 `has_volume` / `has_section` / `part_of_document` / `part_of_volume` / `doc_type` / `volume_type` / `section_anchor` slot。使整篇文档(结构化实体 + 散文)成为图的一等内容,为知识图谱成为完整后端、whole-section 走图奠定本体基础。codegen / subclass-axioms / schema-context card 均兼容,无运行时行为变更。
