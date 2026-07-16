### Changed

- **orchestrator 协议冷热拆分** —— Project Bootstrap（每项目一次）拆至
  `ORCHESTRATOR-BOOTSTRAP-PROTOCOLS.md`，四个异常恢复协议（Rolled-back / TDD Blocked / Crash /
  Truncation）拆至 `ORCHESTRATOR-RECOVERY-PROTOCOLS.md`；热路径文件留触发索引表，
  按需加载（复用 META-PROTOCOLS 拆分先例）。热路径每次加载净省约 1.6k tokens。
- **COMMON-RULES 受众分层外迁** —— 报告撰写规约（编号规则 / Front Matter 约定 /
  问题格式）迁 `.cataforge/references/review-report-spec.md`，保真类 AC 断言口径迁
  `.cataforge/references/fidelity-ac.md`，由报告产出方 / 保真任务消费方按需加载；
  跨 Agent verdict 契约（归因分类 / 三态判定逻辑 / verdict_blocking_semantics）留在
  COMMON-RULES。UNATTENDED_* 与 TDD 相关常量的说明列压缩为「是什么 + 权威指针」。
  全员每次调度省约 1.0k tokens。全部为搬运与指针化，协议语义与调度行为零变化；
  引用锚点已全量同步（分析与决策记录见 `docs/proposals/protocol-docs-slimming.md`）。
