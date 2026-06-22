### Fixed

- **scaffold force-refresh 不再误删运行时状态目录** —— `upgrade apply` / `bootstrap` 的清场阶段过去会把 `.scaffold-manifest.json` 里残留的 `kg/store/*`（旧版本记录、当前已排除出 bundle）当 obsolete 文件删除——典型是只读未 churn 的 RocksDB `CURRENT`——使 KG store 无法打开、doctor 两项 KG 检查 FAIL；gitignored 派生 store 还无法用 git 找回。现把"哪些顶层名不属于 scaffold"（`kg` / `.backups` / `.mcp-state` / `overrides` / 本地记账文件 / 包内模板）收敛为单一谓词，bundle 遍历与 obsolete 清场共用它，stale manifest 条目永不触发删除。
