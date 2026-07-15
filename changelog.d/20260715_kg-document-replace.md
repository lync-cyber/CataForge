### Fixed

- **文档替换语义收敛为单一 domain 原语** —— authoring 重作者同一文档时，旧版本独有的 Section 与重写在同一事务内原子移除（此前 delete 集只含新文档主语，残留 Section 会进 export）；approved 内容冻结门禁收敛为 `document_guard.ensure_document_replaceable` 单点实现，authoring（显式保持 approved 的重写放行）与 ingest / repair（回灌无意图、一律拒绝内容变更且拒绝先于任何写入）语义分级；content-hash 幂等跳过时实体 home 槽位（`cf:source_doc` / `cf:source_section`）仍随新抽取同步（父标题改名等 hash 不变的移动不再留下陈旧归属）。
- **content_hash 契约全链统一** —— writer / transaction / guard 共用 `_quads.content_hash_matches`（64-hex 校验 + 转义），移除 transaction 侧的无校验副本；事务 API 现拒绝非 sha256-hex 的 content_hash。
