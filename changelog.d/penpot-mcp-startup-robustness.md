### Fixed

- **`cataforge penpot` 不再因 `claude mcp list` 超时误报失败** —— `register_claude_mcp` 此前用 10s 硬超时直跑 `claude mcp list`，并让 `subprocess.TimeoutExpired` 直接冒泡；当本机注册了多个远程 MCP server（`claude mcp list` 串行健康检查全部 server）时极易超时，导致一个**已成功启动**的 Penpot MCP 被整体判为退出 1。现把 `claude mcp list` / `claude mcp add` 收敛进 `_run_claude_mcp` best-effort 包装（超时放宽到 30s，超时/缺失 CLI 一律降级为非致命告警 + 手动注册提示），注册步骤不再阻断启动结果。

### Changed

- **`@penpot/mcp` 默认版本由 `latest` 固定到 `2.15.0`** —— `latest` 浮动会在上游 monorepo 引入新的 build-script 依赖时拉起 pnpm 10+ 的构建失败；`PENPOT_MCP_VERSION` 仍可覆盖以跟进更新版本。

### Added

- **Penpot 构建工具链缺失的诊断模式** —— `penpot doctor` / 启动失败报告新增对 `ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL` 及 `Cannot find module …tsc|esbuild` 的识别，命中时提示 Node 版本超出兼容范围、改用 v22 LTS 重试。
