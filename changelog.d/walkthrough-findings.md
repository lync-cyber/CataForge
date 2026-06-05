### Fixed

- **`cataforge phase status` recognises the agile merged phases** —— `planning`（融合 requirements+architecture，同时校验 prd 与 arch）与 `brief` 现为已知阶段；此前被驱动的 agile-lite/agile-prototype 项目会在阶段门禁结构性失败。
- **`phase status` 的 doc-present 检查遵循 `docs/{doc_type}/` 子目录约定** —— 扫描子目录（按 frontmatter `doc_type` 过滤，排除误放的他类文档）并保留扁平路径回退；按约定产出的文档不再被误判缺失。
- **`cataforge event log` / `context *` 继承全局 `--project-dir`** —— 这些子命令此前只读自身 `--project-root`，在 `--project-dir` 隔离场景下会静默写入宿主项目。
- **审查类 skill 的自动事件归属到真实生命周期阶段** —— `CATAFORGE_EVENT_PHASE` 未设时，skill runner 回退读取项目指令文件的「当前阶段」，而非硬编码 `development`。
- **`cataforge context reconcile/finalize/ingest` 在 KG store 缺失时干净退出** —— CLI 边界捕获 `KGStoreNotInitializedError`，渲染为带 `kg init` 提示的 `Error:`，不再泄漏 traceback。

### Changed

- **`context finalize` 对空图自动从 markdown 收敛** —— kg-first 下 markdown-first 授权的内容会被 seed 入图（md→KG，不做有损的反向 re-export），reconcile 不再把整棵文档树报为漂移，「持久化由框架路由」契约成立。
- **`cataforge bootstrap` 为 kg-first 项目初始化 KG store** —— 幂等创建（`--dry-run` 显示为 `kg-init` 步骤），首个 `context write`/`reconcile` 不再撞上缺失的 store。
- **`DOC_REVIEW_L2_SKIP_DOC_TYPES` 改用真实基名 `[brief, changelog]`** —— 移除永不命中的 `-lite` 死项；lite 变体的 Layer 2 短路改由 frontmatter `mode ∈ {agile-lite, agile-prototype}` 驱动。
