### Added

- **`{AGENTS_SRC_DIR}` 运行时占位符** —— 恒解析为 `.cataforge/agents` 源目录（跨平台一致、结构完整、部署后仍可读），供 agent 跨引用 sibling `*PROTOCOLS*.md` 或其他 agent 的 `AGENT.md` 时使用，与 lang-fragment 链接的"指源"策略统一。

### Fixed

- **flat-layout 平台上 agent 协议跨引用悬空** —— Claude Code / OpenCode / Codex 按 `<name>.md` 扁平部署，不复刻源 `<name>/AGENT.md` 子目录及 sibling 协议文件。orchestrator 等用 `{AGENTS_DIR}/<name>/<file>` 写的跨引用会渲染成部署树里并不存在的子路径（如 `.claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md`），运行时定位失败。全部此类跨引用改用 `{AGENTS_SRC_DIR}` 后落到真实源文件，所有平台一致。`_resolve_agents_dir` 的 docstring 同步修正（原先平台分类写反、且声称 flat 平台 sibling 引用"指向源覆盖层"与实现不符）。
