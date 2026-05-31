### Added

- **统一 `context` 父 skill + 分支 reference** —— 新增 `.cataforge/skills/context/SKILL.md` + `references/{navigate,generate,review,consistency,query}.md`,作为文档生命周期 I/O 的单一能力入口(读取/关系查询/生成写入/校验),指向 `cataforge context` / `cataforge docs` 门面;后端(图/文件)与保真度由框架按 `context.strategy` 路由,调用方只表达意图。`context` 计入 framework-review orphan 白名单(与 doc-nav/doc-gen 同类的基础设施 skill)。

### Changed

- **删除散落 harness 的分发复述与实现细节泄露** —— 从 COMMON-RULES §Agent 文档 I/O 契约、doc-nav / doc-gen / doc-review / doc-consistency 的 SKILL 正文、change-guard、task-dep-analysis、ORCHESTRATOR-PROTOCOLS 中移除"KG-active vs legacy 分流"条件复述与 `kg_active_doc_types` / `framework.json.kg` / SPARQL / `cf:` 谓词 / `kg.query` / `render_entity` / `cataforge kg import|reconcile`-作分发条件等实现细节;改为"后端由框架透明路由,调用方不在 prompt 里判断走哪个后端"。skill 计数文档同步 30 → 31。
