### Added

- **KG 渲染泛化 fallback** —— 新增 `export/sparql/_artifact.sparql`（core-slots 查询）+ `export/templates/_base/artifact.md.j2`（继承 artifact_base）。任意 `SoftwareArtifact` 子类无 bespoke 模板时经此渲染，`render_entity` / `compile_to_markdown` / `docs load` 不再对 ui-spec(Page/UIComponent) / dev-plan(Task) / deploy-spec(Deployment 等) 退回文件切片。bespoke 模板（feature/module/testcase/techstack）仍作为带 relations 的覆盖。

### Changed

- **`kg_active_doc_types` 默认扩展为完整业务集** —— 由 `{prd, arch, test}` 改为 `BUSINESS_DOC_TYPES = (prd, arch, ui-spec, dev-plan, test-report, deploy-spec)`，0.5.0 全量支持这些 doc_type 的 KG 读路径。`test`→`test-report`：active 集现用 refs 实际使用的 doc_id，修复 dispatch 按 doc_id 匹配时 `test` 永不命中的接线缺口。
- **doc_type 集合单一事实来源** —— `cataforge.kg._config.BUSINESS_DOC_TYPES` 统一驱动 `DEFAULT_KG_ACTIVE_DOC_TYPES`、ingest `DEFAULT_DOC_TYPES`、doctor `kg_ingestion` 默认集，消除三处硬编码三元组。
- **`kg import` 默认范围跟随 active 集** —— 不带 `--doc-type` 时从 framework.json `kg_active_doc_types` 推导（缺省回退到业务集），使 import 摄取范围与 doctor `kg_ingestion_completeness` 门禁范围一致，避免"激活了却没摄取→门禁红"。
