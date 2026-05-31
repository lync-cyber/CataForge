### Added

- **上下文能力端口 + 保真度路由(application 层)** —— 新增 `cataforge.application.context`:能力端口(`ContextReadPort` / `RelationPort` + `Fidelity` 三态 native/degraded/unsupported)、两个后端(`KgBackend` / `DocBackend`,各自按 operation 声明保真度)、`FidelityRouter`(按 `context.strategy` 装配启用后端,按 operation 取保真度最高且可用者,逐个回退),以及 routed 读门面 `read.py`(`extract` / `extract_batch` / `plan_load` / `resolve_deps` + `cataforge docs load` 编排)。`build_router(project_root)`:`kg-first` 启用 `[kg, doc]`,`doc-only` 仅 `[doc]`。

### Changed

- **读路径分发上抬到 application 层** —— "先试 KG 再兜底文件"的策略分发从 domain 的 `loader` 上抬为 application 的 `FidelityRouter`(orchestration 是 application 职责,非 domain)。`domain.docs.loader` 回落为纯 doc 后端原语(`extract` / `plan_load` / `resolve_deps` 不再触图,不再反向依赖 router);`cataforge docs load` CLI 改由 `application.context.read.main` 编排。非对称由设计:文件后端对 deps/plan_load 仅 `degraded`(静态 `.doc-index.json`),图后端 `native`(`cf:depends_on` 闭包);`doc-only` 下 KG 后端不参与(拓扑选择,非故障兜底)。
