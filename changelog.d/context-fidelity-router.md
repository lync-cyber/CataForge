### Added

- **上下文能力端口 + 保真度路由** —— 新增 `cataforge.domain.context`:能力端口(`ContextReadPort` / `RelationPort` + `Fidelity` 三态 native/degraded/unsupported)、两个后端(`KgBackend` / `DocBackend`,各自按 operation 声明保真度)、`FidelityRouter`(按 `context.strategy` 装配启用后端,按 operation 取保真度最高且可用者,逐个回退)。`build_router(project_root)`:`kg-first` 启用 `[kg, doc]`,`doc-only` 仅 `[doc]`。

### Changed

- **loader 读路径上抬为路由分发** —— `loader.extract` / `plan_load` / `resolve_deps` 不再内联"先试 KG 再兜底文件",改为委派 `FidelityRouter`;原 KG/文件实现分别落为 `KgBackend` / `DocBackend`(文件实现拆为 `loader._doc_extract` / `_doc_plan_load` / `_doc_resolve_deps`)。`doc-only` 方案下 KG 后端不参与(是拓扑选择,非故障兜底);非对称由设计:文件后端对 deps/plan_load 仅 `degraded`(静态 `.doc-index.json`),图后端 `native`(`cf:depends_on` 闭包)。
