### Fixed

- **authoring 失败补偿恢复先前文档** —— `author_document` 提交后校验失败的补偿路径改为快照恢复（复用 `author_entity` 的 prior-quads 契约）：重作者失败时文档、全部先前 Section 与被重写实体回到写前状态，而非删除新写入后留下残缺文档。
- **reconcile 对碰撞 doc_type 的 drift 记录强制 `manual` remediation** —— 文档 id 碰撞使该 doc_type 的 FS 侧不可信，自动 export/ingest 建议一律降级为人工决策。
- **hash-skip home 同步纳入批次补偿** —— `WriteStats.home_synced` 记录已应用的槽位同步，migrate phase 5 回滚与 repair reingest 失败分支经共享的 `writer.revert_home_synced` 反向恢复；stale Section 判定收敛为 `writer.stale_section_iris` 单一定义（ingest 清理与 authoring 替换共用）。
