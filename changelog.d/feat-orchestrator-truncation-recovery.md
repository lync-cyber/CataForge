### Added

- **ORCHESTRATOR-PROTOCOLS §Sub-Agent Truncation Recovery Protocol** —— 与既有 §Agent Crash Recovery 协议区分：crash 是 process 死（无任何输出），truncation 是 token budget 耗尽（artifact 已部分落地，仅 `<agent-result>` JSON 缺失）。截断时主线程不再 blocked，而是按完成度路由：≥70% AC PASS（或 deliverables 齐全）→ 主线程接管收尾（inline-fix lint/typecheck + 补落盘 + 写 EVENT-LOG `state_change` 事件）；<70% → blocked 请求人工。每任务最多 1 次 truncation recovery，第 2 次同任务截断说明 prompt 设计问题，进 retrospective backlog。与 tdd-engine §Mid-Progress Drop Contract 协同：契约预防截断，本协议事后兜底。
