### Fixed

- **pragma_inventory unknown-pragma 判定收紧** —— 候选仅认冒号形态 `cataforge: <verb>`；连字符标识符（`cataforge-plugin.yaml` / `--cataforge-platform` 等）、引号/反引号内的日志前缀与语法示例引用、`allow(<check-id>` 模板占位不再误报（实仓扫描 26 条假阳性清零，手写错语法真阳性保留）。
