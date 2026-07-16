### Fixed

- **doc-review 退役两个过时 Layer 1 守卫** —— `check_line_count`（"超 300 行建议拆分为多个逻辑文档"warn）建议的拆分动作在拆卷废除、一个逻辑文档=一个评审文件的决议下不可执行，且 graph 模式按章节加载后文档行数不再映射任何真实成本；`check_nav_block`（`[NAV]` 块存在性/一致性）的运行时消费方已收敛为零——章节定位走 `.doc-index.json` / KG、必填章节来自模板 frontmatter `required_sections`，且 graph 模式下 `[NAV]` 位于无 authoring 操作触达的 preamble，章节演进后必然漂移误报。随守卫一并移除全部文档模板中的 `[NAV]` 块；`DOC_SPLIT_THRESHOLD_LINES` 常量保留（brief 模式升档信号与 authoring 精简指引仍消费）。
- **code-review Layer 1 架构描述回填** —— `docs/architecture/quality-and-learning.md` 把 Layer 1 描述为"仅 lint + 格式化"、把架构合规整体归入 Layer 2，落后于 registry 现实（22 项机械检查，含 arch_guard / complexity_gate / wiring / ui_fidelity 与 scan 腐化 probe）；问题分类"9 类"复述改为引用权威清单（现行 14 类）。code-review SKILL.md dead-code 探针举例串补列 knip。
