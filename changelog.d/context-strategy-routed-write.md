### Changed

- **`cataforge context` 写入/生命周期命令按 `context.strategy` 路由** —— `finalize` / `ingest` 在 doc-only 项目下路由到文档索引重建（等价 `cataforge docs index`，输出 `indexed N doc(s)`）；`reconcile` 路由到索引完整性校验（orphan / stale / xref / alias / invalid-id），有问题时与 kg-first 漂移同语义 exit 3，索引缺失时 exit 2 并提示 `cataforge docs index`。`write` / `write-narrative` 在 doc-only 下抛出 `ContextStrategyError` 配置错误（说明需要 `context.strategy = "kg-first"`），不再误导性提示 `cataforge kg init`。路由在 application 层（`cataforge.application.context.write`）实现，编程调用方同样生效；kg-first 路径返回契约不变。
