### Added

- **tdd-engine §Mid-Progress Drop Contract** —— LOC > 200 或 AC > 6 的任务在 implementer dispatch prompt（standard Step 3 + light-dispatch）强制注入 4 步落盘契约：先骨架 → 逐 AC 填充 → 每 AC 后跑测试 → 禁止末尾堆批 Edit。治理子代理在 finalize 阶段集中产出导致的 task-notification truncation（100+ tools / 100K+ tokens / 5min+ 后被打断）。light-inline / prototype-inline 不适用（主线程产出，不受子代理 token 额度限制）。失效时由 ORCHESTRATOR-PROTOCOLS §Sub-Agent Truncation Recovery 接管。
