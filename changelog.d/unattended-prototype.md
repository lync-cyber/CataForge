### Added

- **无人值守 building loop 接线 agile-prototype 模式** —— `cataforge unattended build` 按 §项目信息.执行模式 自动路由 building 目标：`agile-prototype` 驱动 brief.md §5 开发任务（完成 / 熔断 ref `brief#tasks`，sprint 参数忽略），其余模式维持 `dev-plan#{sprint}`。新增 `preflight_prototype_brief`（查 brief 存在 + §5 开发任务 + 无未消解 TODO/TBD/FIXME；该模式 checkpoints=none 故不要求 doc-review approved，保证弱于 dev-plan 门）；`guard_frozen_docs` 把 brief 纳入无人值守 file_edit 禁改集（任务卡 status 更新走 `cataforge context` 不受拦）。
