### Changed

- **viz dashboard 脚本复杂度热点拆分 + 模块化** —— `initGraph` / `initCatalogue` / `initFilterTable` 及内联 `apply` 四个复杂度热点（catalogue 曾认知复杂度 167、圈复杂度 73、函数行数 339）拆为一组单一职责顶层辅助函数，抽出共享 `chipVals` / `restoreChips` / `edgesFromNodes` / `resizeGraphsIn` / `resizeChartsIn` 去重，全部降至 code-review 复杂度 fail 阈值（cyclomatic 15 / cognitive 25 / function_lines 120 / nesting 6）以下，残余 warn（`graphStyle` / `initChartMode` / `showPanel` / `initTabKeyboard`）一并清零。`dashboard.js` 单一上帝文件按架构拆为 `dashboard.core/graph/catalogue/table/app.js` 五个模块，渲染时按依赖序拼接内联为单个 `<script>`（core 先执行、app 的 IIFE 末尾跑）。渲染 HTML 内嵌脚本语义不变，行为经全量单元测试 + 真实浏览器 e2e（邻域焦点循环 / roving tabindex / inspector / omnibox）验证保持。

### Fixed

- **窄视口下图表 canvas 撑破页面** —— ECharts 以容器初始（宽）尺寸布局 canvas，视口后续收窄时内层渲染 div 保留旧宽度直至防抖 resize 触发，导致横向溢出（320px 视口下 `scrollWidth` 达 1267px）。给 `.cy` / `.chart` 加 `overflow:hidden` 裁剪渲染面至容器宽度，并为 ECharts tooltip 加 `confine` 防裁剪；窄视口无横向溢出的 e2e 检查恢复绿。
