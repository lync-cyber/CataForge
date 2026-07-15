### Added

- **可选 Design Grill 模式** —— PRD、Architecture 与 UI-design 阶段可在用户显式同意后按决策依赖深度澄清；先核验仓库事实，每问提供推荐、依据与代价，支持跳过、暂停、总结和恢复，完成后回到原阶段流程。

### Fixed

- **冻结文档 Hook 降级声明** —— 四个平台 profile 明确声明 `guard_frozen_docs` 的 native/degraded 策略，避免部署默认值掩盖 Codex 缺少 file-edit matcher 的实际降级。
