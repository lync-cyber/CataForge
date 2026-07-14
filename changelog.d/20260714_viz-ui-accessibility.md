### Changed

- **dashboard 响应式与主题对比度** —— 新增 1024/720 断点：窄视口下 stepper 折叠为「当前阶段 + 阶段 i/N」、tab 组横向滚动、Inspector 改为底部抽屉（bottom-sheet）、图高按视口收敛保证首屏可见内容；图形库配色改由 CSS 主题 token 驱动（`--viz-node-fill/-border/-label`、`--viz-edge`、`--tip-bg/-fg`），OS 明暗主题运行中切换时图与图表实时换肤；对比度校正至 WCAG AA（亮色 `--muted`/`--faint`/`--warn-fg` 加深、暗色 `--faint`/`--accent` 提亮、图例边线随主题），ECharts 动画遵循 `prefers-reduced-motion`；新增对比度守卫测试按计算值断言全部配对 ≥4.5:1（正文）/≥3:1（图形元素）。
- **dashboard 无障碍与信息架构** —— tabs 补全 ARIA（tab↔panel 双向 id 关联、roving tabindex、←→/Home/End 键盘模型、每组独立 labelled tablist）；全局检索升级为完整 combobox（listbox/option、↑↓/Enter/Escape、aria-activedescendant、「无匹配实体」反馈 + aria-live 通报）；Inspector 成为焦点管理的非模态 dialog（打开移焦、Escape 关闭、关闭还原触发元素焦点）；页面获得 `lang="zh-CN"`、h1 与 main 地标；tab 分组重划为 项目交付（覆盖/追溯/任务/架构）· 文档与过程（文档/时间线/腐化）· 框架资产（编排/资产），tab 标签中文化（title 保留 CLI 视图名）；N/A tab 以徽标标识（不再仅靠透明度）；非 SDLC 项目的降级 KPI tile 与 N/A 面板口径一致（不再引导运行不适用的 kg init）。

### Fixed

- **CLI 表格 CJK/emoji 宽度** —— `ui.table` / `ui.kv` 的列宽按终端可见宽度计算（East Asian Wide/Fullwidth 记 2 列、组合字记 0 列），中文单元格不再错位。
- **文档事实修正** —— cli.md：dashboard KPI strip 实为 4 tiles + stepper（非 5 tiles）、语义色为蓝/黄/橙色盲安全对（非绿/黄/红）、coverage 面板为状态表 + Inspector 跨视图跳转（无「点节点直跳 trace」交互）；`quickstart` 描述收敛为「源变更自动重生成、浏览器刷新可见」（非「实时」）；visualization.md：HTML 渲染器路径为 `application/viz/html/` 包，补单文件体积构成说明。
