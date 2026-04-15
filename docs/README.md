# 文档导航（Docs）

本目录集中管理 CataForge 的项目文档，便于开源发布时统一浏览与维护。

## 可用文档

| 文档 | 适用读者 | 内容要点 |
|------|---------|---------|
| [架构与工作流](./workflow.md) | 深入者 | 整体架构、运行时流程、编排协议、平台适配机制 |
| [Agent 与 Skill 清单](./agents-and-skills.md) | 用户 | 13 个 Agent 和 24 个 Skill 的完整说明 |
| [手动验证指南](./manual-verification-guide.md) | 评估者 / 贡献者 | 从 0 到在 IDE 内真实跑通的端到端指南（含安装、真部署、IDE 内观测、故障排查、Verification Report 模板） |

## 视觉资产（`assets/`）

所有文档图表以 SVG 形式放在 [`assets/`](./assets/) 下，遵循统一 [design tokens](./assets/design-tokens.md)（暖纸色 + 琥珀点缀 + 等宽字体的"技术蓝图"风格，与主流 AI 产品视觉刻意区隔）。

<details>
<summary>图表资产索引（8 项 · 点击展开）</summary>

| 资产 | 用途 |
|------|-----|
| [`assets/design-tokens.md`](./assets/design-tokens.md) | 图表 design tokens 单一事实源 |
| [`assets/verification-flow.svg`](./assets/verification-flow.svg) | 手动验证五步流水线（FIG. 01） |
| [`assets/artifact-map.svg`](./assets/artifact-map.svg) | 四平台部署产物对照（FIG. 02） |
| [`assets/architecture-stack.svg`](./assets/architecture-stack.svg) | 五层架构栈（FIG. 03） |
| [`assets/execution-modes.svg`](./assets/execution-modes.svg) | 三种执行模式对比（FIG. 04） |
| [`assets/phase-execution.svg`](./assets/phase-execution.svg) | 阶段执行流程（FIG. 05） |
| [`assets/tdd-engine.svg`](./assets/tdd-engine.svg) | TDD 引擎流程（FIG. 06） |
| [`assets/adapter-translation.svg`](./assets/adapter-translation.svg) | 平台适配器翻译关系（FIG. 07） |

</details>

新增图表前请先阅读 `design-tokens.md`，严格使用其中声明的色板、尺寸、字体与组件约定。

## 维护约定

- 新增文档优先放在 `docs/` 目录；根目录仅保留入口型文档（`README.md`）与兼容跳转。
- 新增 SVG 放在 `docs/assets/`，必须遵循 design tokens；不使用阴影、渐变、位图。
- 所有文档内部链接使用相对路径，便于镜像与 fork。
