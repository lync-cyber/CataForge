### Added

- **KG-first 授权写路径 + `cataforge context` 门面** —— 新增 `application.context.write`:`author_entity`(写时 schema 校验——entity_id↔class 前缀确定性闸门 + 提交后 `validate` 复核,违规即补偿删除并报错)、`write_narrative`(直接把 Section 散文写入图)、`finalize`(KG→md 导出供人审查)、`ingest`(人工修订 md→KG 回灌)、`reconcile_check`(漂移守门)。新增 `cataforge context` CLI 命令族(`read` / `write` / `write-narrative` / `finalize` / `ingest` / `reconcile`)作为统一后端路由门面,调用方不指名图或文件。

### Changed

- **写路径方向翻转为 KG-first** —— 生成走"授权写图(实体 + 叙述 slot,写时校验)→ 导出 markdown 供人审查",取代旧的"先写 md 再 import"投影:结构化实体与散文先入图(经校验),文件树由其派生。`reconcile` 由永久补丁降级为人工回灌后的轻量守门。
