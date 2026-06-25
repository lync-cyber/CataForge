# 可视化架构

> `cataforge viz` 把框架编排与项目结构数据渲染为可版本化的图。命令本身是确定性 CLI（取数 + 渲染、无 LLM 决策分支）。它经一个薄发现型 SKILL.md（`.cataforge/skills/project-visualization/`，instructional、`user-invocable: false`）暴露给 agentic 工作流按情境自主选视图，并由 orchestrator 在 Sprint 收口确定性产出健康度看板作保底；不进 features / capability 注册表（经 `shell_exec` 调用，非 phase-gated / skill-routed）。

设计基线：**单命令产出、可被版本化的产物、零或极少运行时依赖、复用既有数据**。框架内已有结构化数据（知识图谱、文档索引、事件日志、纠偏日志、agent/skill 资产）都有程序化取数入口，viz 只在其上做薄适配与渲染，不重复造数据层。

## 中间表示（IR）

所有数据源归一到三种闭合形态，渲染器只认 IR、不认来源：

| 形态 | 结构 | 承载 |
|------|------|------|
| `Graph` | 节点 + 有向边（各带可选 `label` / `style`） | 追溯链、依赖图、编排拓扑、任务 DAG |
| `Timeline` | 时序事件（`ts` / `label` / `category`） | EVENT-LOG、纠偏趋势 |
| `MetricSeries` | 带标签的数值点（`label` / `value` / `series`） | 覆盖率、腐化计数 |

`View = Graph | Timeline | MetricSeries`（`core/viz/model.py`，纯 frozen dataclass，零依赖）。任何新数据源映射到这三者之一，渲染器无需扩展即可消费。

## collector–renderer 正交

两侧通过 IR 解耦，各自独立扩展：

- **collector**（数据 → IR）：`application/viz/collectors/`，每个是 `collect(root, /, **opts) -> View`（`Collector` Protocol）。
- **renderer**（IR → 输出）：文本渲染器在 `core/viz/render/`（`mermaid` / `dot` / `json_`），HTML 渲染器在 `application/viz/html.py`。

新增数据源只写一个 collector，新增输出格式只写一个 renderer，互不影响。`registry.py` 是唯一扩展缝：`name → collector`、`format → renderer` 两张映射表。`service.generate(view, fmt, root, **opts)` 查表取 collector 产 IR、再交 renderer，是 CLI 与实现之间的薄编排点。

## 层级映射

按复用范围切分，同时满足零冗余与 import-linter 分层契约（`interface → application → {runtime|domain} → adapter → core → utils`）：

| 模块 | 层 | 依据 |
|------|----|------|
| `core/viz/`（IR + 文本渲染核） | core | 纯标准库，被 runtime（task-dep-analysis）与 interface（kg trace）向下复用 |
| `application/viz/`（collectors / html / registry / service） | application | 仅服务 viz 命令面，向下依赖 `domain.kg` / `domain.docs` / `runtime` / `core` |
| `interface/cli/viz_cmd.py` | interface | 薄 CLI：解析 opts → `service.generate` |

文本渲染核落在最低层 `core` 是关键：runtime 与 interface 的既有命令都向下 import 它做唯一的 mermaid 渲染核（见下文收编），若放高层会违反分层。

## 数据流

```
cataforge viz <view> [--format … | --html] [filters]
        │
        ▼
viz_cmd  →  service.generate(view, fmt, root, **opts)
                 │ COLLECTORS[view](root, **opts)        → View(IR)
                 │ RENDERERS[fmt](ir)  或  html.render(ir)
                 ▼
            stdout 或 -o PATH
```

## 渲染形态

同一 IR 之上的能力递进，渲染器/服务包装不同：

- **文本发射**（默认）：IR → Mermaid / DOT / JSON。零依赖，GitHub / IDE / 文档站原生渲染，可内联进文档。
- **自包含 HTML**（`--html`）：IR → 单文件 HTML，内联 vendored JS。无服务进程、零新增运行时依赖（JS 随包分发），提供 zoom / pan / 节点搜索与图表看板。

HTML 渲染器纯按 IR 形态分发：`Graph` → Cytoscape.js（大小图通吃、布局 + 交互），`Timeline` / `MetricSeries` → ECharts（散点时间线 / 柱状指标）。`dashboard` 把全部可用视图聚合进单文件多标签页、两库各内联一次；取不到数据的视图降级为错误面板，不中断整页。

## vendored JS 与打包

`cytoscape.min.js` / `echarts.min.js`（pinned）位于 `application/viz/assets/`，随 `packages = ["src/cataforge"]` 进 wheel，经 `importlib.resources.files("cataforge.application.viz") / "assets" / <name>` 读取并内联进 HTML——无需 force-include 或额外打包配置。打包冒烟测试构建真实 wheel 并断言两个资产被完整打入；HTML 输出零外链，断网可直接打开。

## mermaid 收编

`core.viz.render.mermaid` 是全框架唯一 mermaid 渲染核。原先各处自带的 mermaid 表面统一收编到 viz 入口：

| 旧表面 | 新表面 | 旧命令保留 |
|--------|--------|-----------|
| `kg trace --output mermaid` | `cataforge viz trace` | `kg trace` 的 `table` / `json` 分析 |
| `task-dep-analysis --format mermaid` | `cataforge viz tasks --format mermaid` | `task-dep-analysis --format json` 分析 |

弃用的旧表面登记在 `doctor` 的 `_DEPRECATED_REFS`，使残留提示词引用被标记；提示词内嵌的旧表面额外加 `framework.json` migration_check 提示下游 scaffold 更新。新增 viz 提示词引用须同步 `scripts/checks/check_prompt_cli_drift.py:GROUPS` 加 `viz`。
