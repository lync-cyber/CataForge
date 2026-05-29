### Fixed

- **SessionStart hook 不再自动 deploy** —— `session_context` 此前每次会话启动都 shell out `cataforge deploy`，会把 CLAUDE.md 从模板重写、写 `.scaffold-manifest.json`，污染 tracked 文件并拖慢每次启动。改回其声明职责：仅向 gitignored 的 `docs/EVENT-LOG.jsonl` 追加一条 `session_start` 事件（best-effort，失败仅 stderr 警告，绝不改 tracked 文件）。部署改为显式 `cataforge deploy` / `bootstrap`。framework.json 的 `mc-0.1.5-session-context-simplified` 迁移检查新增 `deploy` 禁词以防回归。
