### Changed

- **Mid-Progress 落盘契约扩展到 reviewer / test-writer / debugger** —— 此前契约仅在 tdd-engine 对 implementer 注入；现为三个 agent 的 AGENT.md 各加一个适配自身产出物的落盘契约（reviewer：先落 REVIEW 报告骨架再逐维度追加；test-writer：先落测试骨架再逐 AC 填充并即时验证；debugger：增量最小修补 + 停滞时返回已排除假设与最佳线索），使长产出子代理被 task-notification truncation 打断时发出 mid-progress checkpoint 而非零产出静默返回。落点选 AGENT.md 因 `claude-code/profile.yaml` 仅 eager 注入 COMMON-RULES、AGENT.md 经 subagent_type 自动加载且不膨胀其他 agent。
