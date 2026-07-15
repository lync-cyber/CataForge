### Changed

- **viz dashboard 脚本复杂度热点拆分 + 模块化** —— `initGraph` / `initCatalogue` / `initFilterTable` 及内联 `apply` 四个复杂度热点（catalogue 曾认知复杂度 167、圈复杂度 73、函数行数 339）拆为一组单一职责顶层辅助函数，抽出共享 `chipVals` / `restoreChips` / `edgesFromNodes` 去重，全部降至 code-review 复杂度 fail 阈值（cyclomatic 15 / cognitive 25 / function_lines 120 / nesting 6）以下。`dashboard.js` 单一上帝文件按架构拆为 `dashboard.core/graph/catalogue/table/app.js` 多文件，渲染时按依赖序拼接内联为单个 `<script>`。渲染 HTML 内嵌脚本语义不变，行为经全量单元测试 + 真实浏览器 e2e（邻域焦点循环 / roving tabindex / inspector / omnibox）验证保持。
