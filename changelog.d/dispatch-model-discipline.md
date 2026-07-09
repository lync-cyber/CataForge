### Added

- **EVENT-LOG 记录派发模型 (`model` 字段)** —— event-log schema 新增可选 `model` 字段、`cataforge event log` 新增 `--model` 选项；tdd-engine 的 tdd_phase 派发事件按档位落 `standard` / `inline`，reflector 复盘时统计派发 model tier 分布、识别低复杂度任务误用 heavy/opus，为子代理成本调优提供数据源。
- **子代理模型选型判据** —— 新增 `.cataforge/references/subagent-model-policy.md`：派发无 frontmatter tier 的通用子代理（general-purpose / Explore / Plan 等）时须显式指定 `model`，默认 sonnet、仅重推理判据用 opus、禁 haiku，堵住省略 `model` 静默继承 opus 会话造成的过度使用；agent-dispatch skill 新增 §模型选型 引用该判据。
