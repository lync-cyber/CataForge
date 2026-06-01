### Changed

- **工作流状态唯一化到平台指令文件** —— `## 项目状态`（当前阶段 / 文档状态等）不再写入独立的 `.cataforge/PROJECT-STATE.md`，而是唯一承载在目标平台的指令文件（claude-code → `CLAUDE.md`，cursor / codex / opencode → `AGENTS.md`）的对应 section。`deploy` 从包内 PROJECT-STATE.md 模板生成指令文件（section-merge 保留运行时状态）；`cataforge phase` 经 `resolve_instruction_file` 跨平台解析并读取指令文件而非 PROJECT-STATE.md。

### Removed

- **下游不再部署 PROJECT-STATE.md** —— scaffold / `upgrade apply` 不再向项目发放 `.cataforge/PROJECT-STATE.md`（降级为包内模板源），消除它与项目根指令文件之间的状态双写冗余。已有项目的指令文件 `## 项目状态` 已由历次 deploy 镜像最新状态，迁移后直接沿用。`mc-0.1.7-cataforge-dir` migration check 不再要求 PROJECT-STATE.md。
