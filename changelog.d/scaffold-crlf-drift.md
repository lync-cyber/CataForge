### Fixed

- **CRLF 行尾不再让 `upgrade apply` 误报漫天 drift** —— 仓库新增 `.gitattributes`（`* text=auto eol=lf`），任何克隆（含 Windows `core.autocrlf=true`）检出与本地 wheel 构建都把 force-include 的 `.cataforge/` scaffold 落成 LF；下游 LF 项目运行 `cataforge upgrade apply` 不再把仅行尾差异的文件逐字节误判为 `drift`（此前可达数十个，足以淹没真实 drift）。
- **KG 运行态 store 不再被当作 scaffold** —— `iter_scaffold_files` 排除顶层 `kg/` 目录，editable 回退遍历本仓 `.cataforge/kg/`、以及脏 wheel 构建打入的 `.cataforge/kg/store/*`（CURRENT / LOG / *.sst 等）不再在每个下游项目报 new/drift。
