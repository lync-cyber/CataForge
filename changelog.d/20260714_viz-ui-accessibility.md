### Fixed

- **CLI 表格 CJK/emoji 宽度** —— `ui.table` / `ui.kv` 的列宽按终端可见宽度计算（East Asian Wide/Fullwidth 记 2 列、组合字记 0 列），中文单元格不再错位。
- **文档事实修正** —— cli.md：dashboard KPI strip 实为 4 tiles + stepper（非 5 tiles）、语义色为蓝/黄/橙色盲安全对（非绿/黄/红）、coverage 面板为状态表 + Inspector 跨视图跳转（无「点节点直跳 trace」交互）；`quickstart` 描述收敛为「源变更自动重生成、浏览器刷新可见」（非「实时」）；visualization.md：HTML 渲染器路径为 `application/viz/html/` 包，补单文件体积构成说明。
