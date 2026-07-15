### Fixed

- **KG 扫描按 canonical `id` 键解析逻辑文档标识** —— ingest 解析改读 frontmatter `id`（模板 / write-doc / finalize 导出统一使用的键；原先只读全无生产者的 `doc_id` 死键），缺失时回退文件名推断；带 distinct `id` 的多份同 doc_type 文件不再被静默折叠为同一 Document 节点。
- **文档 id 碰撞在 scan 生产侧显式拒绝** —— 同批多文件解析到同一逻辑 doc_id 时 `scan_business_docs` 抛 `KGDocumentCollisionError`（对齐既有 entity 碰撞门禁），migrate / repair / reconcile / doctor 全入口覆盖：ingest 拒绝写入、repair 在任何变异前拒绝（此前逐文件重写会互删对方 Section）、reconcile 将碰撞渲染为 finding（`doc_id_collisions`，门禁 `ok=False`）、doctor 报 FAIL 而非崩溃；entity card 导出文件豁免。
