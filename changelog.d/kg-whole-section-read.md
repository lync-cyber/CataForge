### Added

- **whole-section 读路径走图** —— `cataforge docs load <doc>#§N`(无实体的整章引用)在 active doc_type 下从 KG `Section` 节点的 `narrative_body` 解析,不再被拖回文件切片。ingest 现为**每个 §-级标题**(level ≥ 2,含无实体的纯散文章节)落 Section 节点,使整篇文档结构皆为图内容;`loader._try_kg_extract` 按章节号匹配 `cf:section_anchor` 取 body,未命中再回退文件。`narrative_body` 尾部空行裁剪,与文件切片字节对齐。

### Changed

- **Section 发射范围扩到全部 §-级标题** —— Phase 1b 仅落实体所属章节,现落每个 `§` 标题;`contains_entity` 仍只挂在实体的最内层归属章节,父章节承载散文。reconcile 的 Section 对称差随之覆盖全部章节。
