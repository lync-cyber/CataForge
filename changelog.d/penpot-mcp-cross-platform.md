### Fixed

- **Penpot MCP endpoint 跨平台分发** —— 下发用的 `${PENPOT_MCP_URL:-...}` 占位符只有 Claude Code 能在运行时展开;Cursor 用 `${env:VAR}`、Codex 的 TOML `url` 不插值、OpenCode 用 `{env:VAR}`,会把占位符当字面 URL,导致连自托管默认场景都失效。改为 **deploy-time 解析**:spec 存字面默认 url,deploy 读 `PENPOT_MCP_URL` 写入各平台 MCP 配置的字面值,不依赖任何平台的 `${VAR}` 展开能力。

### Added

- **`MCPServerSpec.url_env`** —— 通用字段:命名一个环境变量,deploy 时其值(若设)覆盖 spec 的默认 url(平台显式 override 仍优先)。敏感值(如带 token 的托管 endpoint)留在环境、落各平台 gitignored 的 MCP 配置,不写入 git-tracked 的 spec。
