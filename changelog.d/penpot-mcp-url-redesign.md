### Added

- **`PENPOT_MCP_URL` 统一 MCP endpoint 事实源** —— 下游分发的 `.cataforge/mcp/penpot.yaml` 与 `cataforge penpot remote` 共用此变量；spec 以 `${PENPOT_MCP_URL:-http://localhost:9001/mcp/stream}` 占位符落盘，token 随 env 留在 `.env`（gitignored），不写入 git-tracked spec，运行时由平台（Claude Code / Cursor）展开。
- **自托管插件连接引导** —— `cataforge penpot deploy` 部署后打印浏览器侧步骤（加载 `/plugins/mcp/manifest.json` → Connect）；`status` / `doctor` 澄清「MCP 握手就绪 ≠ 浏览器插件已连」及自托管入口端口（`:9001/mcp/stream`，npx 的 `4400/4401` 不适用于自托管）。

### Changed

- **`cataforge penpot remote` 重定义为托管 MCP** —— 直接注册 `PENPOT_MCP_URL` 指向的托管 endpoint，零本地进程 / Docker / 浏览器插件；终端输出对 URL 中的 `userToken` 做脱敏。

### Deprecated

- **`cataforge penpot mcp-only`（宿主机 npx MCP）** —— 链路脆弱且需浏览器插件常驻，调用时打印迁移提示，引导改用 `remote`（托管）或 `deploy`（自托管）。
