### Changed

- **framework.json schema v2 + 多平台部署状态模型** —— `deployment.default_platform`/`deployment.targets` 取代 `runtime.platform`（旧字段兼容读取，`cataforge config migrate` / `upgrade apply` 自动迁移并备份）；`upgrade.state` 迁至 `.cataforge/state/upgrade.json`；升级合并改为字段级所有权表（用户块 `deployment`/`upgrade.source`/`feedback`/`kg`/`context`/`project`/`claude_md_limits`/`git` 与未知顶层键一律保留）。部署记录 per-platform（`.cataforge/state/deploy/<platform>/`），四平台可长期共存：单平台 redeploy 不触碰他平台产物，跨平台共享路径受保护集防误删，deploy 全程持项目级锁并发拒绝，配置写入带锁防 lost update。
- **doctor 平台化** —— 新增 `--platform <id>|all`；deploy integrity/provenance 以 per-platform manifest 为权威（不再要求 MCP 条件产物）；migration checks 支持 `platforms` 适用范围；指令文件 hygiene 按平台 profile 选择 CLAUDE.md/AGENTS.md；新增 agent skill 依赖可达性与 §项目状态 投影 drift 检查。
- **平台身份与共享指令文件** —— hook 命令携带 `--cataforge-platform`（opencode TS plugin 注入 env、claude-code settings 注入 `CATAFORGE_PLATFORM`），多平台项目身份歧义时 hook 显式失败；共享 AGENTS.md 的 `运行时:` 按声明 targets 集合渲染、平台占位符中性化，换序部署字节稳定；codex/opencode 的 agent skills 依赖降级为正文内 `.cataforge/skills/<id>/SKILL.md` 读取指令。

### Added

- **`cataforge config` 子命令** —— `validate` / `get` / `explain`（值 + 来源层：env > local > framework > legacy > default）/ `set`（白名单路径、同值不落盘、`--dry-run`）/ `migrate`；`.cataforge/config.local.json` 本机覆盖层（gitignored）。
