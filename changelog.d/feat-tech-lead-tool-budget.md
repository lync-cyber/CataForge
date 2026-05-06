### Added

- **tech-lead 任务卡 `expected_tool_budget` 软门禁** —— dev-plan 任务卡可选标 `expected_tool_budget: ~N`（典型值 80-120，仅 standard 模式有意义）。tech-lead AGENT.md 新增决策矩阵（LOC × AC × Modules → light 内联 / light 拆分 / standard + mid-progress 三档），用于反向校验 `tdd_mode` 选择是否合理。orchestrator 在 dispatch 时按本字段做 sanity check（>150 警告，>200 阻断并建议拆分为 light 序列）。配合 tdd-engine §Mid-Progress Drop Contract（standard + LOC > 250 时强制注入 4 步落盘契约）。
