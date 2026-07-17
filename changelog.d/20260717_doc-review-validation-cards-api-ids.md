# ## Fixed

- **doc-review L1 对 validation 任务卡豁免 TDD 字段检查** —— dev-plan 任务完整性检查识别
  `task_kind: validation` / 标题 `[VALIDATION]` 的任务卡并从 deliverables / tdd_acceptance 计数中
  排除；此前 task-decomp 允许产出的验证卡（不进 TDD、无这两字段）会被同一门禁双 FAIL。
- **doc-review L1 的 ARCH 分节失败文案列出违规条目 id** —— 「N个API中M个缺少入参定义」等三条
  规则（API 入参 / 模块功能映射 / 实体字段表）现附具体 id 列表（前 5 项 + 总数后缀），与 KG
  覆盖检查文案同构；此前只报计数，修复者需逐个试错定位。
