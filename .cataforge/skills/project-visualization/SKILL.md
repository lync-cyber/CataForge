---
name: project-visualization
description: "项目可视化 — 把既有知识图谱/文档索引/事件日志/纠偏日志/agent-skill 资产渲染为图、时间线、指标看板(经 cataforge viz CLI)。当需要看编排拓扑、需求→模块→任务→测试追溯链、Feature 覆盖盲区、架构模块依赖、文档依赖(stale 高亮)、任务 DAG 关键路径、SDLC 阶段进度、腐化趋势,或想要一张项目健康度总览看板时使用。文本(mermaid/dot/json)可内联文档,--html 出单文件离线交互页。"
argument-hint: "<视图: overview|framework|assets|trace|coverage|arch|docs|tasks|phase|timeline|decay|dashboard>"
suggested-tools: shell_exec
depends: []
disable-model-invocation: false
user-invocable: false
---

# 项目可视化 (project-visualization)

把框架内既有的结构化数据渲染为可读图形。viz 不造数据、不做内容决策,只在 KG / doc-index / EVENT-LOG / CORRECTIONS / agent-skill 资产之上做薄渲染,经 `cataforge viz <视图>` CLI 调用。

## 能力边界
- 能做: 渲染追溯链、覆盖矩阵、依赖图、编排拓扑、阶段进度、时间线、腐化趋势为图/时间线/指标
- 不做: 不查实体属性(走 `cataforge kg query` / `cataforge context read`)、不出审查 verdict(走 code-review / doc-review / framework-review)、不写业务数据

## 输入规范
按"想看什么"选视图（先用 `cataforge viz status` 看哪些视图当前有数据），可选 `--format mermaid|dot|json` / `--html` / `-o PATH` / 各视图过滤参数:

| 想看什么 | 命令 |
|---------|------|
| 项目健康 KPI(阶段/文档/覆盖/断链/腐化,默认 json) | `cataforge viz overview` |
| 编排拓扑 orchestrator→phase→agent→skill | `cataforge viz framework` |
| agent / skill / rules 资产目录(元数据+体量+依赖图,--html 出可搜索面板) | `cataforge viz assets` |
| 需求→模块→任务→测试追溯链 / 断链 | `cataforge viz trace [实体ID]` |
| Feature 实现 / 测试覆盖盲区 | `cataforge viz coverage` |
| 架构模块依赖图 | `cataforge viz arch` |
| 文档依赖图(stale / 断链高亮) | `cataforge viz docs` |
| 任务 DAG + 关键路径 | `cataforge viz tasks` |
| SDLC 阶段进度 + 门禁状态 | `cataforge viz phase` |
| EVENT-LOG 时间线 | `cataforge viz timeline` |
| 纠偏 / 腐化趋势 | `cataforge viz decay` |
| 全视图聚合健康度看板 | `cataforge viz dashboard` |

## 输出规范
- 默认文本: `--format mermaid|dot|json`,GitHub / IDE / 文档站原生渲染,可 `-o PATH` 内联进文档
- 交互页: `--html` 产单文件离线 HTML(图用 Cytoscape.js、看板用 ECharts),零外链可断网打开
- 实时看板: `cataforge viz quickstart` 一键生成 + 本地服务 + 开浏览器 + 监听源数据刷新

## Anti-Patterns
- 禁止: 手写 mermaid 依赖图嵌进 dev-plan — 应跑 `cataforge viz tasks --format mermaid`,同一图算法产出,手写易与关键路径标注漂移
- 禁止: 把 viz 当数据源去查实体属性 — 结构化查询走 `cataforge kg query` / `cataforge context read`,viz 只渲染既有数据
- 禁止: 用 viz 产物替代质量门禁结论 — 覆盖图能暴露盲区但不出 verdict,审查结论仍由 code-review / doc-review 给出
- 避免: 无视空数据源直接跑视图 — KG / EVENT-LOG 未就绪时先 `cataforge viz status` 再选有数据的视图
