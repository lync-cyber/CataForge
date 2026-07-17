### Fixed

- **Bootstrap 补初始 phase_start 落盘** —— ORCHESTRATOR-BOOTSTRAP-PROTOCOLS Step 10 进入初始阶段前
  先 `cataforge event log --event phase_start --phase {当前阶段}`；此前 `cataforge phase status --entry`
  的入口校验硬性期望该事件而协议无任何落盘动作，每个新项目都会在入口卡一次。
- **`project.languages` 获得受支持写入路径** —— `cataforge config set project.languages <ids>` 纳入
  白名单（逗号分隔，同义词经 canonical 归一化，空值恢复 marker 自动检测）；Bootstrap Step 7 的
  setup 命令附带 `--language {Step 1 确认的语言}` 把用户口述技术栈固化进配置——从零项目在
  Bootstrap 时点无 marker 文件，检测型 backfill 恒为空，TDD lang_rules 语言细则链因此全程不加载。
