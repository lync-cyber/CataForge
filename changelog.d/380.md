### Added

- **viz 接入 agentic 工作流** —— 新增薄发现型 skill `.cataforge/skills/project-visualization/`（instructional、`user-invocable: false`），让 orchestrator 与各 agent 按情境（看覆盖盲区 / 追溯断链 / 核对架构 / 项目健康度总览…）自主发现并调用 `cataforge viz <视图>`；其情境→视图映射承载「定向」语义。orchestrator 在每个 Sprint 收口（短路与正常路径均适用）确定性产出 `docs/viz/dashboard.html` 健康度看板作保底。此前 viz 命令面虽已实现，但工作流缺发现面与触发点，富视图从不被自动调用。
